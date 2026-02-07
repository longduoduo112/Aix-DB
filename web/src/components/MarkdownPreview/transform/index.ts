type ContentResult = {
  content: string
  done?: never
  progress?: never
}

type DoneResult = {
  done: true
  content?: never
  progress?: never
}

type ProgressResult = {
  progress: any
  content?: never
  done?: never
}

type TransformResult = ContentResult | DoneResult | ProgressResult
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
    
    // 检查是否是控制信号或结构化数据（从 store 传来的 JSON 字符串）
    if (typeof content === 'string' && content.trim()) {
      try {
        const json = JSON.parse(content.trim())
        // 检查流结束信号
        if (json && json.done === true) {
          return {
            done: true,
          }
        }
        // 检查是否是进度信息（需要同时有 step 和 stepName）
        if (json && json.type === 'step_progress' && json.step && json.stepName && json.status && json.progressId) {
          return {
            progress: json,
          }
        }
        // 提取 messageType/content 格式的数据（store 解析 t02 后传来的）
        if (json.messageType !== undefined && json.content !== undefined) {
          return {
            content: json.content || '',
          }
        }
      } catch (error) {
        // 不是 JSON，继续处理为普通内容
      }
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
        // 处理进度信息（严格按照协议格式检查）
        // 协议格式：{type: "step_progress", step: string, stepName: string, status: "start"|"complete", progressId: string, ...}
        if (json && json.type === 'step_progress' && json.step && json.stepName && json.status && json.progressId) {
          return {
            progress: json,
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
        // 处理进度信息（严格按照协议格式检查）
        // 协议格式：{type: "step_progress", step: string, stepName: string, status: "start"|"complete", progressId: string, ...}
        if (json && json.type === 'step_progress' && json.step && json.stepName && json.status && json.progressId) {
          return {
            progress: json,
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
    let content = ''
    if (readValue instanceof Uint8Array) {
      const textDecoder = new TextDecoder('utf-8')
      content = textDecoder.decode(readValue, {
        stream: true,
      })
    } else {
      content = readValue
    }
    
    // 处理 data: 前缀的格式（SSE格式，splitStream处理后可能还保留）
    if (typeof content === 'string' && content.trim().startsWith('data: ')) {
      try {
        const jsonStr = content.trim().substring(6).trim() // 移除 "data: " 前缀
        if (jsonStr && jsonStr !== '[DONE]') {
          const json = JSON.parse(jsonStr)
          // 处理进度信息（dataType为t14）
          if (json.dataType === 't14' && json.data) {
            const progressData = json.data
            // 严格按照协议格式检查进度信息
            if (progressData && progressData.type === 'step_progress' && progressData.step && progressData.status && progressData.progressId) {
              return {
                progress: progressData,
              }
            }
          }
          // 服务端 SSE 保活事件，不追加任何内容，避免长时间等待时连接被断开
          if (json.dataType === 'keepalive') {
            return { content: '' }
          }
          // 处理自定义格式：{"data":{"messageType":"continue","content":"..."},"dataType":"t02"}
          if (json.dataType === 't02' && json.data && json.data.content !== undefined) {
            return {
              content: json.data.content || '',
            }
          }
          // 处理业务数据：{"data":{...},"dataType":"t04"}
          if (json.dataType === 't04' && json.data) {
            // t04数据由其他逻辑处理，这里不处理
            return {
              content: '',
            }
          }
        }
      } catch (error) {
        // 如果不是 JSON，继续处理
      }
    }
    
    // 检查是否是进度信息（从 store 传来的 JSON 字符串）
    // 协议格式：{type: "step_progress", step: string, stepName: string, status: "start"|"complete", progressId: string, ...}
    if (typeof content === 'string' && content.trim()) {
      try {
        const json = JSON.parse(content.trim())
        // 处理 dataType 为 t14 的格式：{"data":{...},"dataType":"t14"}
        if (json.dataType === 't14' && json.data) {
          const progressData = json.data
          // 严格按照协议格式检查进度信息
          if (progressData && progressData.type === 'step_progress' && progressData.step && progressData.status && progressData.progressId) {
            return {
              progress: progressData,
            }
          }
        }
        // 严格按照协议格式检查进度信息（直接是progress对象的情况）
        if (json && json.type === 'step_progress' && json.step && json.status && json.progressId) {
          return {
            progress: json,
          }
        }
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
        // 如果不是 JSON，继续处理
      }
    }
    
    // 原来的逻辑：直接解析 JSON
    try {
      const stream = JSON.parse(content)
      return {
        content: stream.content || '',
      }
    } catch (error) {
      return {
        content: content || '',
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
      // 按分隔符拆分，将完整的行 enqueue，保留最后不完整的部分在 buffer 中
      buffer = processParts(buffer, controller, splitOn)
    },
    flush(controller) {
      if (buffer.trim() !== '') {
        controller.enqueue(buffer)
      }
    },
  })
}
