type ContentResult = {
  content: string
  done?: never
}

type DoneResult = {
  done: true
  content?: never
}

type TransformResult = ContentResult | DoneResult
type TransformFunction<T = any> = (rawValue: T, ...args: any) => TransformResult

/**
 * 转义处理响应值为 data: 的 json 字符串
 * 如: 科大讯飞星火大模型的 response
 */
export const parseJsonLikeData = (content) => {
  if (content.startsWith('data: ')) {
    const dataString = content.substring(6).trim()
    if (dataString === '[DONE]') {
      return {
        done: true,
      }
    }
    try {
      return JSON.parse(dataString)
    } catch (error) {
      console.error('JSON parsing error:', error)
    }
  }
  return null
}

/**
 * 大模型映射列表
 */
export const LLMTypes = [
  {
    label: '模拟数据模型',
    modelName: 'standard',
  },
  {
    label: 'Spark 星火大模型',
    modelName: 'spark',
  },
  {
    label: 'Qwen 2大模型',
    modelName: 'qwen2',
  },
  {
    label: 'SiliconFlow 硅基流动大模型',
    modelName: 'siliconflow',
  },
] as const

export type TransformStreamModelTypes = (typeof LLMTypes)[number]['modelName']

/**
 * 用于处理不同类型流的值转换器
 */
export const transformStreamValue: Record<
  TransformStreamModelTypes,
  TransformFunction
> = {
  standard(readValue: Uint8Array, textDecoder: TextDecoder) {
    let content = ''
    if (readValue instanceof Uint8Array) {
      content = textDecoder.decode(readValue, {
        stream: true,
      })
    } else {
      content = readValue
    }
    return {
      content,
    }
  },
  spark(readValue) {
    // 如果是字符串，尝试解析 JSON
    if (typeof readValue === 'string') {
      try {
        const json = JSON.parse(readValue)
        // 处理自定义格式：{"messageType":"continue","content":"..."}
        if (json.messageType !== undefined && json.content !== undefined) {
          return {
            content: json.content || '',
          }
        }
        // 处理自定义格式：{"data":{"messageType":"continue","content":"..."},"dataType":"t02"}
        if (json.data && json.data.content !== undefined) {
          return {
            content: json.data.content || '',
          }
        }
      } catch (error) {
        // 如果不是 JSON，继续使用原来的逻辑
      }
    }

    // 原来的逻辑：处理 data: 前缀的格式
    const stream = parseJsonLikeData(readValue)
    if (stream) {
      if (stream.done) {
        return {
          done: true,
        }
      }
      return {
        content: stream.choices[0].delta.content || '',
      }
    }
    return {
      content: '',
    }
  },
  siliconflow(readValue) {
    // 与 spark 类似，使用相同的逻辑
    // 如果是字符串，尝试解析 JSON
    if (typeof readValue === 'string') {
      try {
        const json = JSON.parse(readValue)
        // 处理自定义格式：{"messageType":"continue","content":"..."}
        if (json.messageType !== undefined && json.content !== undefined) {
          return {
            content: json.content || '',
          }
        }
        // 处理自定义格式：{"data":{"messageType":"continue","content":"..."},"dataType":"t02"}
        if (json.data && json.data.content !== undefined) {
          return {
            content: json.data.content || '',
          }
        }
      } catch (error) {
        // 如果不是 JSON，继续使用原来的逻辑
      }
    }

    // 原来的逻辑：处理 data: 前缀的格式
    const stream = parseJsonLikeData(readValue)
    if (stream) {
      if (stream.done) {
        return {
          done: true,
        }
      }
      return {
        content: stream.choices[0].delta.content || '',
      }
    }
    return {
      content: '',
    }
  },
  qwen2(readValue) {
    // 如果是字符串，尝试解析 JSON
    if (typeof readValue === 'string') {
      try {
        const json = JSON.parse(readValue)
        // 处理自定义格式：{"messageType":"continue","content":"..."}
        if (json.messageType !== undefined && json.content !== undefined) {
          return {
            content: json.content || '',
          }
        }
        // 处理自定义格式：{"data":{"messageType":"continue","content":"..."},"dataType":"t02"}
        if (json.data && json.data.content !== undefined) {
          return {
            content: json.data.content || '',
          }
        }
        // 处理原有的 qwen2 格式：直接包含 content
        if (json.content !== undefined) {
          return {
            content: json.content || '',
          }
        }
      } catch (error) {
        // 如果不是 JSON，返回空内容
        return {
          content: '',
        }
      }
    }
    
    // 原来的逻辑：直接解析 JSON
    try {
      const stream = JSON.parse(readValue)
      return {
        content: stream.content || '',
      }
    } catch (error) {
      return {
        content: '',
      }
    }
  },
}

const processParts = (
  buffer,
  controller: TransformStreamDefaultController,
  splitOn,
) => {
  const parts = buffer.split(splitOn)
  parts.slice(0, -1).forEach((part) => {
    if (part.trim() !== '') {
      controller.enqueue(part)
    }
  })
  return parts[parts.length - 1]
}

export const splitStream = (splitOn): TransformStream<string, string> => {
  let buffer = ''
  return new TransformStream({
    transform(chunk, controller) {
      buffer += chunk

      if (buffer.trim().startsWith('data:')) {
        buffer = processParts(buffer, controller, splitOn)
      } else {
        // 尝试是否能够直接解析为 JSON
        try {
          JSON.parse(buffer)
          buffer = processParts(buffer, controller, splitOn)
        } catch (error) {
          // 如果解析失败，按原文本处理
          controller.enqueue(chunk)
          buffer = ''
        }
      }
    },
    flush(controller) {
      if (buffer.trim() !== '') {
        controller.enqueue(buffer)
      }
    },
  })
}
