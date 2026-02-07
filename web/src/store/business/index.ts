import { defineStore } from 'pinia'
import * as GlobalAPI from '@/api'
import * as TransformUtils from '@/components/MarkdownPreview/transform'

export interface BusinessState {
  writerList: any
  qa_type: any
  task_id: any
  record_id: number | null // 记录ID，用于查询SQL语句
  file_list: {
    source_file_key: string
    parse_file_key: string
    file_size: string
  }[]
  suggestedDisabled: boolean
}

export const useBusinessStore = defineStore('business-store', {
  state: (): BusinessState => {
    return {
      writerList: {},
      // 全局报错问答类型
      qa_type: 'COMMON_QA',
      // 全局保存文件问答地址
      file_list: [],
      // 全局保存dify 任务id
      task_id: '',
      // 全局保存记录ID，用于查询SQL语句
      record_id: null,
      // 全局推荐问题禁用状态
      suggestedDisabled: false,
    }
  },
  actions: {
    /**
     * 更新 问答类型
     */
    update_qa_type(qa_type) {
      this.qa_type = qa_type
    },
    // 添加单个文件url到数组
    add_file(file_url: any) {
      this.file_list.push(file_url)
    },

    // 清空文件url数组
    clear_file_list() {
      this.file_list = []
    },
    /**
     * 清空记录ID
     */
    clear_record_id() {
      this.record_id = null
    },
    // 删除单个文件url
    remove_file(source_file_key: string) {
      const index = this.file_list.findIndex(
        (file) => file.source_file_key === source_file_key,
      )
      if (index !== -1) {
        this.file_list.splice(index, 1)
      }
    },
    update_writerList(writerList) {
      this.writerList = writerList
    },
    clearWriterList() {
      this.writerList = {}
    },
    update_task_id(task_id) {
      this.task_id = task_id
    },
    clear_task_id() {
      this.task_id = ''
    },
    // 设置推荐问题禁用状态
    set_suggested_disabled(disabled: boolean) {
      this.suggestedDisabled = disabled
    },
    /**
     * Event Stream 调用大模型python服务接口
     */
    async createAssistantWriterStylized(
      uuid,
      chat_id,
      writerOid,
      data,
    ): Promise<{
      error: number
      reader: ReadableStreamDefaultReader<string> | null
      needLogin: boolean
      permissionDenied?: boolean
      errorMessage?: string
    }> {
      return new Promise((resolve) => {
        const query_str = data.text
        const file_list = data.file_list
        const qa_type = data.qa_type || this.qa_type
        const datasource_id = data.datasource_id
        const processResponse = async (res) => {
          if (res.status === 401) {
            // 登录失效
            return {
              error: 1,
              reader: null,
              needLogin: true,
              permissionDenied: false,
            }
          } else if (res.status === 403) {
            // 权限被拒绝
            try {
              const errorData = await res.json()
              return {
                error: 1,
                reader: null,
                needLogin: false,
                permissionDenied: true,
                errorMessage: errorData.msg || '您没有访问该数据源的权限，请联系管理员授权。',
              }
            } catch (e) {
              return {
                error: 1,
                reader: null,
                needLogin: false,
                permissionDenied: true,
                errorMessage: '您没有访问该数据源的权限，请联系管理员授权。',
              }
            }
          } else if (res.status === 200) {
            const reader = res.body
              .pipeThrough(new TextDecoderStream())
              .pipeThrough(TransformUtils.splitStream('\n'))
              .pipeThrough(
                new TransformStream({
                  transform: (chunk, controller) => {
                    try {
                      // 只移除 SSE 的 data: 前缀，不用 split 避免内容中包含 data: 导致误切割
                      const trimmed = chunk.trim()
                      if (!trimmed.startsWith('data:')) return
                      const chunkData = trimmed.slice(5).trim()
                      if (!chunkData) return
                      const jsonChunk = JSON.parse(chunkData)
                      if (jsonChunk.task_id) {
                        // 调用已有的更新方法来更新 task_id
                        this.update_task_id(
                          jsonChunk.task_id,
                        )
                      }
                      switch (jsonChunk.dataType) {
                        case 't11':
                          controller.enqueue(
                            JSON.stringify({
                              content: `问题: ${query_str}`,
                            }),
                          )
                          break
                        case 't02':
                          if (
                            jsonChunk.data
                            && jsonChunk.data.content
                          ) {
                            controller.enqueue(
                              JSON.stringify(
                                jsonChunk.data,
                              ),
                            )
                          }
                          break
                        case 't04':
                          this.writerList = jsonChunk
                          break
                        case 't12':
                          // 处理record_id，存储到store中以便后续使用
                          if (jsonChunk.data && jsonChunk.data.record_id) {
                            this.record_id = jsonChunk.data.record_id
                          }
                          break
                        case 't14':
                          // 处理步骤进度信息，直接传递给前端组件显示
                          if (jsonChunk.data && jsonChunk.data.type === 'step_progress') {
                            controller.enqueue(
                              JSON.stringify({
                                type: 'step_progress',
                                step: jsonChunk.data.step,
                                stepName: jsonChunk.data.stepName,
                                status: jsonChunk.data.status,
                                progressId: jsonChunk.data.progressId,
                              }),
                            )
                          }
                          break
                        case 't99':
                          // 流结束标记，通知下游关闭
                          controller.enqueue(
                            JSON.stringify({
                              done: true,
                            }),
                          )
                          break
                        default:
                                                // 可以在这里处理其他类型的 dataType
                      }
                    } catch (e) {
                      console.error(
                        'Error processing chunk:',
                        e,
                      )
                    }
                  },
                  flush: (controller) => {
                    controller.terminate()
                  },
                }),
              )
              .getReader()

            return {
              error: 0,
              reader,
              needLogin: false,
              permissionDenied: false,
            }
          } else {
            return {
              error: 1,
              reader: null,
              needLogin: false,
              permissionDenied: false,
            }
          }
        }

        // 调用后端接口拿大模型结果
        GlobalAPI.createOllama3Stylized(query_str, qa_type, uuid, chat_id, file_list, datasource_id)
          .then(async (res) => resolve(await processResponse(res)))
          .catch((err) => {
            console.error('Request failed:', err)
            resolve({
              error: 1,
              reader: null,
              needLogin: false,
              permissionDenied: false,
            })
          })
      })
    },
  },
})
