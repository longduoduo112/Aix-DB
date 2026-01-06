<script lang="ts" setup>
import { NButton, NMessageProvider, NSpin, useMessage } from 'naive-ui'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  dsId: number
  dragging?: boolean
}>()

const message = useMessage()
const loading = ref(false)
const nodeIds = ref<any[]>([])
const cells = ref<any[]>([])
let graph: any = null
const containerRef = ref<HTMLElement | null>(null)
const parentContainerRef = ref<HTMLElement | null>(null)
const containerHeight = ref<number>(800)
let resizeObserver: ResizeObserver | null = null
let keyDownHandler: ((e: KeyboardEvent) => void) | null = null // 保存键盘事件处理函数引用
const selectedEdge = ref<any>(null) // 当前选中的 edge

const LINE_HEIGHT = 48
const NODE_WIDTH = 240

// Edge 配置（优化大规模数据表血缘关系）
const edgeOption = {
  connector: {
    name: 'normal',
  },
  attrs: {
    line: {
      stroke: '#A8ADB4', // 更柔和的默认颜色，减少视觉干扰
      strokeWidth: 1.5, // 更细的线条，适合大规模数据
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      // 添加透明度，减少重叠时的视觉混乱
      opacity: 0.7,
    },
    text: {
      fontSize: 11,
      fill: '#666',
      fontFamily: 'inherit',
      fontWeight: 400,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
    },
  },
  labels: [
    {
      attrs: {
        text: {
          fontSize: 11,
          fill: '#666',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          fontWeight: 400,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
        },
        rect: {
          fill: '#fff',
          stroke: '#E5E7EB',
          strokeWidth: 1,
          rx: 4,
          ry: 4,
          padding: 4,
        },
      },
      position: {
        distance: 0.5,
      },
    },
  ],
}

const initGraph = (): Promise<void> => {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined') {
      reject(new Error('Window is undefined'))
      return
    }

    if (graph) {
      resolve()
      return
    }

    const tryGetContainer = (retries = 10): void => {
      const container = document.getElementById('relationship-container') || containerRef.value
      if (container) {
        initializeGraph(container, resolve, reject)
      } else if (retries > 0) {
        setTimeout(() => tryGetContainer(retries - 1), 50)
      } else {
        reject(new Error('Graph container not ready after retries'))
      }
    }

    tryGetContainer()
  })
}

const initializeGraph = (container: HTMLElement, resolve: () => void, reject: (error: Error) => void) => {
  import('@antv/x6').then(({ Graph, Shape }) => {
    Graph.registerPortLayout(
      'erPortPosition',
      (portsPositionArgs: any[]) => {
        return portsPositionArgs.map((_, index) => ({
          position: {
            x: 0,
            y: (index + 1) * LINE_HEIGHT + 15,
          },
          angle: 0,
        }))
      },
      true,
    )

    Graph.registerNode(
      'er-rect',
      {
        inherit: 'rect',
        markup: [
          { tagName: 'path', selector: 'top' },
          { tagName: 'rect', selector: 'body' },
          { tagName: 'text', selector: 'label' },
          { tagName: 'path', selector: 'div' },
        ],
        attrs: {
          top: {
            fill: '#BBBFC4',
            refX: 0,
            refY: 0,
            d: 'M0 5C0 2.23858 2.23858 0 5 0H235C237.761 0 240 2.23858 240 5H0Z',
          },
          rect: {
            strokeWidth: 0.5,
            stroke: '#DEE0E3',
            fill: '#F5F6F7',
            refY: 5,
          },
          div: {
            fillRule: 'evenodd',
            clipRule: 'evenodd',
            fill: '#646A73',
            refX: 12,
            refY: 21,
            fontSize: 14,
            d: 'M1.4773 1.47724C1.67618 1.27836 1.94592 1.16663 2.22719 1.16663H11.7729C12.0541 1.16663 12.3239 1.27836 12.5227 1.47724C12.7216 1.67612 12.8334 1.94586 12.8334 2.22713V11.7728C12.8334 12.0541 12.7216 12.3238 12.5227 12.5227C12.3239 12.7216 12.0541 12.8333 11.7729 12.8333H2.22719C1.64152 12.8333 1.16669 12.3585 1.16669 11.7728V2.22713C1.16669 1.94586 1.27842 1.67612 1.4773 1.47724ZM2.33335 5.83329V8.16662H4.66669V5.83329H2.33335ZM2.33335 9.33329V11.6666H4.66669V9.33329H2.33335ZM5.83335 11.6666H8.16669V9.33329H5.83335V11.6666ZM9.33335 11.6666H11.6667V9.33329H9.33335V11.6666ZM11.6667 8.16662V5.83329H9.33335V8.16662H11.6667ZM8.16669 5.83329H5.83335V8.16662H8.16669V5.83329ZM11.6667 2.33329H2.33335V4.66663H11.6667V2.33329Z',
          },
          label: {
            fill: '#1F2329',
            fontSize: 14,
          },
        },
        ports: {
          groups: {
            list: {
              markup: [
                { tagName: 'rect', selector: 'portBody' },
                { tagName: 'text', selector: 'portNameLabel' },
                { tagName: 'text', selector: 'portCommentLabel' },
              ],
              attrs: {
                portBody: {
                  width: NODE_WIDTH,
                  height: LINE_HEIGHT,
                  stroke: '#DEE0E3',
                  strokeWidth: 0.5,
                  fill: '#ffffff',
                  magnet: true,
                },
                portNameLabel: {
                  ref: 'portBody',
                  refX: 12,
                  refY: 9.5,
                  fontSize: 13,
                  fontWeight: 500,
                  textAnchor: 'left',
                  fill: '#1F2329',
                  textWrap: { width: 120, height: 20, ellipsis: true },
                },
                portCommentLabel: {
                  ref: 'portBody',
                  refX: 12,
                  refY: 24,
                  fontSize: 11,
                  textAnchor: 'left',
                  fill: '#8B8E94',
                  textWrap: { width: 200, height: 16, ellipsis: true },
                },
              },
              position: 'erPortPosition',
            },
          },
        },
      },
      true,
    )

    graph = new Graph({
      mousewheel: {
        enabled: true,
        modifiers: ['ctrl', 'meta'],
        factor: 1.05,
      },
      container,
      autoResize: true,
      panning: true,
      connecting: {
        allowBlank: false,
        router: {
          name: 'manhattan',
          args: {
            padding: 8, // 增加间距，减少交叉
            startDirections: ['top', 'right', 'bottom', 'left'],
            endDirections: ['top', 'right', 'bottom', 'left'],
          },
        },
        connector: { name: 'normal' },
        validateEdge({ edge }: any) {
          const obj = edge.store.data
          if (!obj.target.port || obj.target.cell === obj.source.cell) {
            return false
          }
          return true
        },
        createEdge() {
          // 创建新 edge 时，确保不包含 tools，删除按钮只在 hover 时显示
          const newEdge = new Shape.Edge({
            ...edgeOption,
            tools: [], // 确保新创建的 edge 默认没有 tools
          })
          return newEdge
        },
      },
      // 优化大规模数据性能
      async: true, // 启用异步渲染
      // 减少不必要的重绘
      background: {
        color: '#f5f6f7',
      },
    })

    // ✅ 点击选中 edge
    graph.on('edge:click', ({ edge, e }: any) => {
      e.stopPropagation()
      // 取消之前选中的 edge
      if (selectedEdge.value && selectedEdge.value !== edge) {
        selectedEdge.value.setAttrs({
          line: {
            stroke: '#A8ADB4',
            strokeWidth: 1.5,
            opacity: 0.7,
          },
        })
      }
      // 选中当前 edge
      selectedEdge.value = edge
      edge.setAttrs({
        line: {
          stroke: '#18a0ff',
          strokeWidth: 2.5,
          opacity: 1,
        },
      })
    })

    // ✅ hover 时触发蓝色虚线流动动画
    graph.on('edge:mouseenter', ({ edge }: any) => {
      if (!edge || !edge.view) {
        return
      }
      // 如果已经选中，不改变样式
      if (selectedEdge.value === edge) {
        return
      }
      
      const path = edge.view.$('.x6-edge-path')[0]
      if (path) {
        path.classList.add('edge-flow')
        // 改变颜色为蓝色，增加宽度和透明度
        edge.setAttrs({
          line: {
            stroke: '#18a0ff',
            strokeWidth: 2.5,
            opacity: 1,
          },
        })
      }
    })

    graph.on('edge:mouseleave', ({ edge }: any) => {
      if (!edge || !edge.view) {
        return
      }
      // 如果已选中，保持选中样式
      if (selectedEdge.value === edge) {
        return
      }
      
      const path = edge.view.$('.x6-edge-path')[0]
      if (path) {
        path.classList.remove('edge-flow')
        // 恢复原始颜色和样式
        edge.setAttrs({
          line: {
            stroke: '#A8ADB4',
            strokeWidth: 1.5,
            opacity: 0.7,
          },
        })
      }
    })

    // ✅ 点击空白处取消选中
    graph.on('blank:click', () => {
      if (selectedEdge.value) {
        selectedEdge.value.setAttrs({
          line: {
            stroke: '#A8ADB4',
            strokeWidth: 1.5,
            opacity: 0.7,
          },
        })
        selectedEdge.value = null
      }
    })

    // ✅ 监听 edge 添加事件，确保新添加的 edge 默认没有 tools
    graph.on('edge:added', ({ edge }: any) => {
      if (edge) {
        // 确保新添加的 edge 默认没有 tools
        nextTick(() => {
          edge.removeTools()
        })
      }
    })

    // ✅ 键盘删除选中的 edge
    keyDownHandler = (e: KeyboardEvent) => {
      // 按 Delete 或 Backspace 键删除选中的 edge
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedEdge.value) {
        e.preventDefault()
        e.stopPropagation()
        const edgeId = selectedEdge.value.id
        graph.removeEdge(edgeId)
        message.success('已删除关系线')
        selectedEdge.value = null
      }
    }
    
    // 监听键盘事件（在容器上）
    nextTick(() => {
      if (container && keyDownHandler) {
        container.setAttribute('tabindex', '0')
        container.addEventListener('keydown', keyDownHandler)
        // 点击容器时自动获得焦点
        container.addEventListener('click', () => {
          container.focus()
        })
      }
    })

    resolve()

    // 节点工具
    graph.on('node:mouseenter', ({ node }: any) => {
      node.addTools({
        name: 'button',
        args: {
          markup: [
            {
              tagName: 'circle',
              selector: 'button',
              attrs: { r: 7, cursor: 'pointer' },
            },
            {
              tagName: 'path',
              selector: 'icon',
              attrs: {
                'd': 'M -3 -3 3 3 M -3 3 3 -3',
                'stroke': 'white',
                'stroke-width': 2,
                'cursor': 'pointer',
              },
            },
          ],
          x: 0,
          y: 0,
          offset: { x: 165, y: 28 },
          onClick({ view }: any) {
            graph.removeNode(view.cell.id)
            nodeIds.value = nodeIds.value.filter((ele) => ele !== view.cell.id)
          },
        },
      })
    })

    graph.on('node:mouseleave', ({ node }: any) => {
      node.removeTools()
    })

    resolve()
  }).catch((error) => {
    console.error('Failed to load X6:', error)
    message.error('图形库加载失败，请刷新页面重试')
    reject(error)
  })
}

// ... 其余方法（getTableData, addNode, clickTable, save, handleDrop 等）保持不变 ...
// （此处省略以节省篇幅，实际使用时保留原逻辑）

const getTableData = async () => {
  loading.value = true
  try {
    const url = new URL(`${location.origin}/sanic/datasource/get/${props.dsId}`)
    const response = await fetch(url, { method: 'POST' })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const result = await response.json()
    if (result.code === 200) {
      const ds = result.data || {}
      const data = ds.table_relation || ds.tableRelation || []
      nodeIds.value = data.filter((ele: any) => ele.shape === 'er-rect').map((ele: any) => ele.id)
      await nextTick()
      if (!graph) {
        await initGraph()
      }
      await nextTick()
      if (!graph) {
        message.error('图形未初始化，请重试')
        return
      }
      if (!Array.isArray(data) || data.length === 0) {
        graph.clearCells()
        cells.value = []
        nodeIds.value = []
        return
      }
      cells.value = []
      data.forEach((item: any) => {
        if (item.shape === 'edge') {
          // 创建 edge 时应用优化后的配置和路由
          // 移除可能存在的 tools 配置，确保默认不显示删除按钮
          const { tools, ...edgeData } = item
          cells.value.push(
            graph.createEdge({
              ...edgeData,
              ...edgeOption,
              router: {
                name: 'manhattan',
                args: {
                  padding: 8,
                  startDirections: ['top', 'right', 'bottom', 'left'],
                  endDirections: ['top', 'right', 'bottom', 'left'],
                },
              },
            }),
          )
        } else {
          cells.value.push(
            graph.createNode({
              ...item,
              height: LINE_HEIGHT + 15,
              width: NODE_WIDTH,
            }),
          )
        }
      })
      graph.resetCells(cells.value)
      // 确保所有 edge 默认不显示 tools
      await nextTick()
      graph.getEdges().forEach((edge: any) => {
        edge.removeTools()
      })
      // 确保容器尺寸更新后再调整视图
      await nextTick()
      // 延迟一点时间确保所有元素渲染完成后再调整视图
      setTimeout(() => {
        if (graph && cells.value.length > 0) {
          graph.zoomToFit({ padding: 20, maxScale: 1 })
        }
      }, 100)
    }
  } catch (error) {
    console.error('获取表关系数据失败:', error)
    message.error('获取表关系数据失败')
  } finally {
    loading.value = false
  }
}

const addNode = async (node: any) => {
  if (!graph) {
    try {
      await initGraph()
    } catch (error) {
      console.error('初始化图形失败:', error)
      message.error('初始化图形失败，请重试')
      return
    }
  }
  if (!graph) {
    message.error('图形未初始化，请重试')
    return
  }
  graph.addNode(
    graph.createNode({
      ...node,
      attrs: {
        label: {
          text: node.label,
          textAnchor: 'left',
          refX: 34,
          refY: 28,
          textWrap: { width: 120, height: 24, ellipsis: true },
        },
      },
      height: LINE_HEIGHT + 15,
      width: NODE_WIDTH,
    }),
  )
}

const clickTable = async (table: any) => {
  loading.value = true
  try {
    const url = new URL(`${location.origin}/sanic/datasource/fieldList/${table.id}`)
    const response = await fetch(url, { method: 'POST' })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const result = await response.json()
    if (result.code === 200) {
      const fields = result.data || []
      const node = {
        id: table.id,
        shape: 'er-rect',
        label: table.table_name,
        width: 150,
        height: 24,
        position: {
          x: table.x || Math.random() * 400,
          y: table.y || Math.random() * 400,
        },
        ports: fields.map((ele: any) => ({
          id: ele.id,
          group: 'list',
          attrs: {
            portNameLabel: { text: ele.field_name },
            portCommentLabel: { text: ele.field_comment || ele.comment || ele.remark || '' },
          },
        })),
      }
      nodeIds.value = [...nodeIds.value, table.id]
      await nextTick()
      await addNode(node)
    }
  } catch (error) {
    console.error('添加表节点失败:', error)
    message.error('添加表节点失败')
  } finally {
    loading.value = false
  }
}

const save = async () => {
  if (!graph) {
    message.warning('没有可保存的数据')
    return
  }
  try {
    const cells = graph.toJSON().cells || []
    const url = new URL(`${location.origin}/sanic/datasource/tableRelation`)
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ds_id: props.dsId,
        relations: cells,
      }),
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const result = await response.json()
    if (result.code === 200) {
      message.success('保存成功')
      await getTableData()
    } else {
      message.error(result.msg || '保存失败')
    }
  } catch (error) {
    console.error('保存表关系失败:', error)
    message.error('保存表关系失败')
  }
}

const handleDrop = (e: DragEvent) => {
  const tableData = e.dataTransfer?.getData('table')
  if (tableData) {
    try {
      const table = JSON.parse(tableData)
      if (!table.id) {
        return
      }
      const rect = (e.currentTarget as HTMLElement | null)?.getBoundingClientRect()
      if (rect) {
        table.x = e.clientX - rect.left
        table.y = e.clientY - rect.top
      } else {
        table.x = (e as any).layerX
        table.y = (e as any).layerY
      }
      clickTable(table)
    } catch (error) {
      console.error('解析表数据失败:', error)
      message.error('添加表失败')
    }
  }
}

defineExpose({ clickTable, loadRelation: getTableData })

const updateContainerHeight = () => {
  if (parentContainerRef.value) {
    const rect = parentContainerRef.value.getBoundingClientRect()
    containerHeight.value = rect.height || 800
    if (graph && containerRef.value) {
      nextTick(() => {
        const containerRect = containerRef.value?.getBoundingClientRect()
        if (containerRect) {
          graph.resize(containerRect.width, containerRect.height)
          // 如果有数据，自动调整视图以显示所有内容
          if (cells.value.length > 0) {
            setTimeout(() => {
              graph.zoomToFit({ padding: 20, maxScale: 1 })
            }, 50)
          }
        }
      })
    }
  }
}

onMounted(() => {
  nextTick(() => {
    updateContainerHeight()
    if (parentContainerRef.value && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => updateContainerHeight())
      resizeObserver.observe(parentContainerRef.value)
    }
  })
  window.addEventListener('resize', updateContainerHeight)
  getTableData()
})

onBeforeUnmount(() => {
  // 移除键盘事件监听
  if (containerRef.value && keyDownHandler) {
    containerRef.value.removeEventListener('keydown', keyDownHandler)
    keyDownHandler = null
  }
  if (graph) {
    graph.dispose()
    graph = null
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  window.removeEventListener('resize', updateContainerHeight)
  selectedEdge.value = null
})

const dragover = () => {}

const zoomIn = () => graph && graph.zoom(Math.min((graph.zoom() || 1) * 1.2, 3), { absolute: true })
const zoomOut = () => graph && graph.zoom(Math.max((graph.zoom() || 1) / 1.2, 0.1), { absolute: true })
const zoomToFit = () => graph && graph.zoomToFit({ padding: 10, maxScale: 1 })
const zoomReset = () => graph && graph.zoom(1)
</script>

<template>
  <n-message-provider>
    <div
      ref="parentContainerRef"
      class="table-relationship"
    >
      <!-- ✅ 新增：SVG 内嵌动画样式 -->
      <svg
        style="position: fixed; top: -9999px"
        xmlns:xlink="http://www.w3.org/1999/xlink"
      >
        <defs>
          <filter
            id="filter-dropShadow-v0-3329848037"
            x="-1"
            y="-1"
            width="3"
            height="3"
            filterUnits="objectBoundingBox"
          >
            <feDropShadow
              stdDeviation="4"
              dx="1"
              dy="2"
              flood-color="#1F23291F"
              flood-opacity="0.65"
            />
          </filter>
        </defs>
      </svg>

      <n-spin :show="loading">
        <div
          id="relationship-container"
          ref="containerRef"
          class="container"
          :style="{ minHeight: `${containerHeight}px` }"
          tabindex="0"
          @drop.prevent="handleDrop"
          @dragover.prevent
          @click="() => containerRef?.focus()"
        ></div>

        <div
          v-if="!nodeIds.length && !loading"
          class="relationship-empty"
        >
          请从左侧拖拽表到此处，或点击表添加到关系图中
        </div>
      </n-spin>

      <div
        v-show="props.dragging"
        class="drag-mask"
        @drop.prevent.stop="handleDrop"
        @dragover.prevent.stop="dragover"
      ></div>

      <div
        v-if="nodeIds.length"
        class="zoom-controls"
      >
        <n-button
          size="small"
          quaternary
          @click.stop="zoomIn"
        >
          <template #icon>
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M8 3V13M3 8H13"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </template>
        </n-button>
        <n-button
          size="small"
          quaternary
          @click.stop="zoomOut"
        >
          <template #icon>
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M3 8H13"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </template>
        </n-button>
        <n-button
          size="small"
          quaternary
          @click="zoomToFit"
        >
          <template #icon>
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M2 6L6 2M10 2L14 6M14 10L10 14M6 14L2 10"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </template>
        </n-button>
        <n-button
          size="small"
          quaternary
          @click="zoomReset"
        >
          <template #icon>
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M8 2V8H14"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </template>
        </n-button>
      </div>

      <div class="save-btn">
        <n-button
          v-if="graph"
          type="primary"
          @click="save"
        >
          保存
        </n-button>
      </div>

      <!-- 删除提示 -->
      <div
        v-if="selectedEdge"
        class="delete-hint"
      >
        <span>已选中关系线，按 <kbd>Delete</kbd> 或 <kbd>Backspace</kbd> 删除</span>
      </div>
    </div>
  </n-message-provider>
</template>

<style lang="scss" scoped>
.table-relationship {
  width: 100%;
  height: 100%;
  position: relative;
  background-color: #f5f6f7;
  overflow: hidden;
}

.zoom-controls {
  position: absolute;
  right: 16px;
  top: 16px;
  z-index: 10;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 10%);
  padding: 4px;
  display: flex;
  gap: 4px;
  align-items: center;
}

.save-btn {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 10;
}

.delete-hint {
  position: absolute;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  z-index: 10;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 12px;
  pointer-events: none;
  animation: fadeIn 0.3s ease;

  kbd {
    background: rgba(255, 255, 255, 0.2);
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
    font-size: 11px;
    margin: 0 2px;
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

.drag-mask {
  width: 100%;
  height: 100%;
  position: absolute;
  left: 0;
  top: 0;
  z-index: 100;
  pointer-events: all;
}

.relationship-empty {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #999;
  pointer-events: none;
  z-index: 1;
}

.container {
  font-size: 14px;
  user-select: text;
  overflow: hidden;
  outline: none;
  touch-action: none;
  box-sizing: border-box;
  position: relative;
  min-width: 400px;
  width: 100%;
  height: 100%;
  background-color: #f5f6f7;

  :deep(.x6-graph),
  :deep(.x6-graph-svg) {
    width: 100%;
    height: 100%;
    // 启用硬件加速，优化大规模数据性能
    transform: translateZ(0);
    will-change: transform;
  }

  :deep(.x6-edge-tool) {
    cursor: pointer;
    
    circle {
      transition: all 0.2s ease;
      
      &:hover {
        r: 9 !important;
        filter: drop-shadow(0 2px 4px rgba(255, 77, 79, 0.3));
      }
    }
  }

  :deep(.x6-node-tool) circle {
    fill: #18a0ff !important;
  }

  :deep(.x6-node) {
    cursor: move;
    filter: url("#filter-dropShadow-v0-3329848037");
  }

  :deep(.x6-edge) {
    cursor: pointer;
    transition: opacity 0.2s ease;
    // 减少不必要的重绘
    vector-effect: non-scaling-stroke;
    
    &:hover {
      opacity: 1 !important;
    }
  }

  :deep(.x6-edge-label) {
    font-size: 12px;
    font-weight: 500;
    fill: #666;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  :deep(.x6-edge-label rect) {
    fill: #fff;
    stroke: #E5E7EB;
    stroke-width: 1;
    rx: 4;
    ry: 4;
  }
}

@keyframes flow-edge {
  to { stroke-dashoffset: -20; }
}

.edge-flow {
  stroke-dasharray: 8, 8;
  animation: flow-edge 1.5s linear infinite;
  stroke-linecap: round;
  filter: drop-shadow(0 0 2px rgba(24, 160, 255, 0.4));
}
</style>
