import * as GlobalAPI from '@/api'
import * as TransformUtils from '@/components/MarkdownPreview/transform'

import router from '@/router'

const businessStore = useBusinessStore()
const userStore = useUserStore()
// const router = useRouter() // Removed to avoid inject() warning outside setup

type StreamData = {
  dataType: string
  content?: string
  data?: any
}

// 历史对话记录数据渲染转换逻辑
const processSingleResponse = (res) => {
  if (res.body) {
    const reader = res.body
      .pipeThrough(new TextDecoderStream())
      .pipeThrough(TransformUtils.splitStream('\n'))
      .pipeThrough(
        new TransformStream<string, string>({
          transform: (
            chunk: string,
            controller: TransformStreamDefaultController,
          ) => {
            try {
              const jsonChunk = JSON.parse(chunk)
              switch (jsonChunk.dataType) {
                case 't11':
                  controller.enqueue(
                    JSON.stringify(jsonChunk),
                  )
                  break
                case 't02':
                  if (jsonChunk.data) {
                    controller.enqueue(
                      JSON.stringify(jsonChunk.data),
                    )
                  }
                  break
                case 't04':
                  businessStore.update_writerList(
                    JSON.parse(jsonChunk.data),
                  )
                  break
                default:
                  break
              }
            } catch (e) {
              console.log('Error processing chunk:', e)
            }
          },
          flush: (controller: TransformStreamDefaultController) => {
            controller.terminate()
          },
        }),
      )
      .getReader()

    return {
      error: 0,
      reader,
    }
  } else {
    return {
      error: 1,
      reader: null,
    }
  }
}

interface TableItem {
  uuid: string
  key: string
  chat_id: string
  qa_type: string
  datasource_id?: number
  datasource_name?: string
}

// 请求接口查询对话历史记录
export const fetchConversationHistory = async function fetchConversationHistory(
  isInit: Ref<boolean>,
  conversationItems: Ref<
    Array<{
      chat_id: string
      qa_type: string
      question: string
      file_key: {
        source_file_key: string
        parse_file_key: string
        file_size: string
      }[]
      role: 'user' | 'assistant'
      reader: ReadableStreamDefaultReader | null
    }>
  >,
  tableData: Ref<TableItem[]>,
  currentRenderIndex: Ref<number>,
  row,
  searchText: string,
  page = 1,
  limit = 20,
  append = false,
) {
  try {
    // 清空现有的 conversationItems（仅在重新加载当前对话时）
    if (!append && row?.chat_id) {
      conversationItems.value = []
    }

    const res = await GlobalAPI.query_user_qa_record(
      page,
      limit,
      searchText,
      row?.chat_id,
    )
    if (res.status === 401) {
      userStore.logout()
      setTimeout(() => {
        router.replace('/login')
      }, 500)
    } else if (res.ok) {
      const data = await res.json()
      if (data && Array.isArray(data.data?.records)) {
        const records = data.data.records

        // 初始化左右对话侧列表数据
        if (isInit.value || !row?.chat_id) {
          const nextTableRows = records.map((chat: any) => ({
            uuid: chat.uuid,
            key: chat.question.trim(),
            chat_id: chat.chat_id,
            qa_type: chat.qa_type,
            datasource_id: chat.datasource_id,
            datasource_name: chat.datasource_name,
          }))

          if (append) {
            const exists = new Set(tableData.value.map((item) => item.chat_id))
            const filtered = nextTableRows.filter(
              (item) => !exists.has(item.chat_id),
            )
            tableData.value = [...tableData.value, ...filtered]
          } else {
            tableData.value = nextTableRows
          }
        }

        const itemsToAdd: any[] = []
        // 用户问题
        let question_str = ''
        for (const record of records) {
          // 问答类型
          let qa_type_str = ''
          // 对话id
          let chat_id_str = ''
          // 文件keys
          let file_key_json = []
          // 自定义id
          let uuid_str = ''
          const streamDataArray: StreamData[] = [];
          [
            'question',
            'to2_answer',
            'to4_answer',
            'qa_type',
            'chat_id',
            'file_key',
            'uuid',
          ].forEach((key: string) => {
            if (record.hasOwnProperty(key)) {
              switch (key) {
                case 'uuid':
                  uuid_str = record[key]
                  break
                case 'qa_type':
                  qa_type_str = record[key]
                  break
                case 'chat_id':
                  chat_id_str = record[key]
                  break
                case 'file_key':
                  // console.log(record[key])
                  if (record[key]) {
                    file_key_json = JSON.parse(record[key])
                  }
                  break
                case 'question':
                  question_str = record[key]
                  break
                case 'to2_answer':
                  try {
                    streamDataArray.push({
                      dataType: 't02',
                      data: {
                        content: JSON.parse(record[key])
                          .data
                          .content,
                      },
                    })
                  } catch (e) {
                    console.log(e)
                  }
                  break
                case 'to4_answer':
                  if (
                    record[key] !== null
                    && record[key] !== undefined
                  ) {
                    streamDataArray.push({
                      dataType: 't04',
                      data: record[key],
                    })
                  }
                  break
              }
            }
          })

          if (streamDataArray.length > 0 && row?.chat_id) {
            const stream = createStreamFromValue(streamDataArray) // 创建新的流
            const { error, reader } = processSingleResponse({
              status: 200, // 假设状态码总是 200
              body: stream,
            })

            if (error === 0 && reader) {
              itemsToAdd.push({
                uuid: uuid_str,
                chat_id: chat_id_str,
                qa_type: qa_type_str,
                question: question_str,
                file_key: file_key_json,
                role: 'user',
                reader: null,
              })

              itemsToAdd.push({
                chat_id: chat_id_str,
                qa_type: qa_type_str,
                question: question_str,
                file_key: [],
                role: 'assistant',
                reader,
              })
            }
          }
        }

        // 只有在查看具体对话时才更新右侧内容
        if (row?.chat_id) {
          conversationItems.value = append
            ? [...conversationItems.value, ...itemsToAdd]
            : itemsToAdd
          // 这里删除对话后需要重置当前渲染索引
          currentRenderIndex.value = append
            ? conversationItems.value.length - 1
            : 0
        }

        return {
          currentPage: data.data?.current_page ?? page,
          totalPages: data.data?.total_pages ?? 1,
          totalCount: data.data?.total_count ?? records.length,
        }
      }
    } else {
      console.log('Request failed with status:', res.status)
    }
  } catch (error) {
    console.log('An error occurred while querying QA records:', error)
  }
}

function createStreamFromValue(valueArray: StreamData[]) {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller: ReadableStreamDefaultController) {
      valueArray.forEach((value) => {
        controller.enqueue(encoder.encode(`${JSON.stringify(value)}\n`))
      })
      controller.close()
    },
  })
}
