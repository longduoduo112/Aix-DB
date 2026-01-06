<script lang="ts" setup>
import { NButton, NMessageProvider, NSpin, useMessage } from 'naive-ui'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetch_neo4j_relation } from '@/api/datasource'

const props = defineProps<{
  dsId: number
}>()

const message = useMessage()
const loading = ref(false)
const nodeIds = ref<string[]>([])
const cells = ref<any[]>([])
let graph: any = null
const containerRef = ref<HTMLElement | null>(null)
const parentContainerRef = ref<HTMLElement | null>(null)
const containerHeight = ref<number>(800)
let resizeObserver: ResizeObserver | null = null
const selectedNode = ref<any>(null)

// Neo4j 风格配置
const NODE_COLORS = [
  '#68BDF6', // 浅蓝色
  '#6DCE9E', // 浅绿色
  '#FFB84D', // 浅橙色
  '#FF6B9D', // 浅粉色
  '#C44569', // 浅紫色
  '#4ECDC4', // 青色
  '#95E1D3', // 薄荷绿
  '#F38181', // 浅红色
]

// Edge 配置 - Neo4j 风格
const edgeOption = {
  connector: {
    name: 'smooth',
  },
  attrs: {
    line: {
      stroke: '#68BDF6', // Neo4j 蓝色
      strokeWidth: 2,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      targetMarker: {
        name: 'classic',
        size: 7,
        fill: '#68BDF6',
        stroke: '#68BDF6',
      },
    },
    text: {
      fontSize: 11,
      fill: '#333',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      fontWeight: 500,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
    },
  },
  labels: [
    {
      attrs: {
        text: {
          fontSize: 11,
          fill: '#333',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          fontWeight: 500,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
        },
        rect: {
          fill: '#fff',
          stroke: '#68BDF6',
          strokeWidth: 1.5,
          rx: 4,
          ry: 4,
          padding: 6,
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
      const container = document.getElementById('neo4j-relationship-container') || containerRef.value
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
    // 注册 Neo4j 风格的椭圆形节点
    Graph.registerNode(
      'neo4j-circle',
      {
        inherit: 'ellipse',
        width: 120,
        height: 60,
        attrs: {
          body: {
            fill: '#68BDF6', // Neo4j 默认蓝色
            stroke: '#4A90E2',
            strokeWidth: 2.5,
            refRx: '50%',
            refRy: '50%',
          },
          label: {
            fill: '#fff',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
            textWrap: {
              width: 100,
              height: 50,
              ellipsis: true,
            },
            textVerticalAnchor: 'middle',
            textAnchor: 'middle',
          },
        },
        ports: {
          groups: {
            top: {
              position: {
                name: 'ellipse',
                args: {
                  angle: -90,
                },
              },
              attrs: {
                circle: {
                  r: 4,
                  magnet: true,
                  stroke: '#68BDF6',
                  strokeWidth: 1,
                  fill: '#fff',
                },
              },
            },
            right: {
              position: {
                name: 'ellipse',
                args: {
                  angle: 0,
                },
              },
              attrs: {
                circle: {
                  r: 4,
                  magnet: true,
                  stroke: '#68BDF6',
                  strokeWidth: 1,
                  fill: '#fff',
                },
              },
            },
            bottom: {
              position: {
                name: 'ellipse',
                args: {
                  angle: 90,
                },
              },
              attrs: {
                circle: {
                  r: 4,
                  magnet: true,
                  stroke: '#68BDF6',
                  strokeWidth: 1,
                  fill: '#fff',
                },
              },
            },
            left: {
              position: {
                name: 'ellipse',
                args: {
                  angle: 180,
                },
              },
              attrs: {
                circle: {
                  r: 4,
                  magnet: true,
                  stroke: '#68BDF6',
                  strokeWidth: 1,
                  fill: '#fff',
                },
              },
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
      // 禁用连接功能（只读模式）
      connecting: {
        enabled: false,
      },
      // 禁用节点和边的选择框
      selecting: {
        enabled: false,
      },
      // 禁用节点移动（可选，如果希望完全只读可以启用）
      // translating: {
      //   restrict: true,
      // },
      background: {
        color: '#ffffff', // 白色背景
      },
    })

    // 节点点击事件 - 显示节点信息（只读模式）
    graph.on('node:click', ({ node }: any) => {
      const nodeData = node.getData()
      selectedNode.value = {
        id: node.id,
        name: node.attr('label/text') || node.id.replace('neo4j_', ''),
        category: 'Table',
        properties: nodeData || {},
      }
    })

    // 节点悬停效果（只读模式，不显示删除按钮）
    graph.on('node:mouseenter', ({ node }: any) => {
      node.setAttrs({
        body: {
          strokeWidth: 3,
        },
      })
    })

    graph.on('node:mouseleave', ({ node }: any) => {
      node.setAttrs({
        body: {
          strokeWidth: 2.5,
        },
      })
    })

    resolve()
  }).catch((error) => {
    console.error('Failed to load X6:', error)
    message.error('图形库加载失败，请刷新页面重试')
    reject(error)
  })
}

const getNeo4jData = async () => {
  loading.value = true
  try {
    const response = await fetch_neo4j_relation(props.dsId)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const result = await response.json()
    if (result.code === 200) {
      const relations = result.data || []
      
      if (!graph) {
        await initGraph()
      }
      await nextTick()
      if (!graph) {
        message.error('图形未初始化，请重试')
        return
      }
      
      if (!Array.isArray(relations) || relations.length === 0) {
        graph.clearCells()
        cells.value = []
        nodeIds.value = []
        return
      }

      // 构建节点和边的映射
      const tableMap = new Map<string, { x: number; y: number }>()
      const edges: any[] = []
      const tableFields = new Map<string, Set<string>>()

      // 收集所有表和字段
      relations.forEach((rel: any) => {
        const fromTable = rel.from_table
        const toTable = rel.to_table
        const fieldRelation = rel.field_relation || ''

        if (!tableMap.has(fromTable)) {
          tableMap.set(fromTable, { x: Math.random() * 400, y: Math.random() * 400 })
        }
        if (!tableMap.has(toTable)) {
          tableMap.set(toTable, { x: Math.random() * 400, y: Math.random() * 400 })
        }

        // 解析字段关系
        if (fieldRelation) {
          const match = fieldRelation.match(/(\w+)\.(\w+)=(\w+)\.(\w+)/)
          if (match) {
            const [, , fromField, , toField] = match
            if (!tableFields.has(fromTable)) {
              tableFields.set(fromTable, new Set())
            }
            if (!tableFields.has(toTable)) {
              tableFields.set(toTable, new Set())
            }
            tableFields.get(fromTable)!.add(fromField)
            tableFields.get(toTable)!.add(toField)
          }
        }

        edges.push({
          from: fromTable,
          to: toTable,
          fieldRelation,
        })
      })

      // 创建节点 - Neo4j 风格
      cells.value = []
      nodeIds.value = []
      
      const tableArray = Array.from(tableMap.entries())
      tableArray.forEach(([tableName, pos], index) => {
        const nodeId = `neo4j_${tableName}`
        nodeIds.value.push(nodeId)
        
        // 为每个节点分配不同的颜色
        const colorIndex = index % NODE_COLORS.length
        const nodeColor = NODE_COLORS[colorIndex]
        // 计算深色边框（将颜色变暗）
        const hex = nodeColor.replace('#', '')
        const r = Math.max(0, parseInt(hex.substr(0, 2), 16) - 30)
        const g = Math.max(0, parseInt(hex.substr(2, 2), 16) - 30)
        const b = Math.max(0, parseInt(hex.substr(4, 2), 16) - 30)
        const borderColor = `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
        
        // 使用椭圆形节点，Neo4j 风格
        const node = graph.createNode({
          id: nodeId,
          shape: 'neo4j-circle',
          label: tableName,
          width: 120,
          height: 60,
          attrs: {
            body: {
              fill: nodeColor,
              stroke: borderColor,
              strokeWidth: 2.5,
            },
            label: {
              fill: '#fff',
              fontSize: 13,
              fontWeight: 600,
            },
          },
          position: {
            x: pos.x || Math.random() * 600,
            y: pos.y || Math.random() * 400,
          },
          data: {
            tableName,
            color: nodeColor,
            fields: Array.from(tableFields.get(tableName) || []),
          },
        })
        cells.value.push(node)
      })

      // 创建边 - Neo4j 风格
      edges.forEach((edge) => {
        const fromNodeId = `neo4j_${edge.from}`
        const toNodeId = `neo4j_${edge.to}`
        
        // 简化关系标签，只显示关系类型
        let relationLabel = 'REFERENCES'
        if (edge.fieldRelation) {
          // 提取字段关系作为标签
          const match = edge.fieldRelation.match(/(\w+)\.(\w+)=(\w+)\.(\w+)/)
          if (match) {
            const [, , fromField, , toField] = match
            relationLabel = `${fromField} → ${toField}`
          }
        }

        const edgeNode = graph.createEdge({
          ...edgeOption,
          source: { cell: fromNodeId },
          target: { cell: toNodeId },
          labels: relationLabel ? [
            {
              attrs: {
                text: {
                  text: relationLabel,
                },
              },
            },
          ] : [],
        })
        cells.value.push(edgeNode)
      })

      graph.resetCells(cells.value)
      
      await nextTick()
      setTimeout(() => {
        if (graph && cells.value.length > 0) {
          graph.zoomToFit({ padding: 20, maxScale: 1 })
        }
      }, 100)
    }
  } catch (error) {
    console.error('获取 Neo4j 关系数据失败:', error)
    message.error('获取 Neo4j 关系数据失败')
  } finally {
    loading.value = false
  }
}

const updateContainerHeight = () => {
  if (parentContainerRef.value) {
    const rect = parentContainerRef.value.getBoundingClientRect()
    containerHeight.value = rect.height || 800
    if (graph && containerRef.value) {
      nextTick(() => {
        const containerRect = containerRef.value?.getBoundingClientRect()
        if (containerRect) {
          graph.resize(containerRect.width, containerRect.height)
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

const zoomIn = () => graph && graph.zoom(Math.min((graph.zoom() || 1) * 1.2, 3), { absolute: true })
const zoomOut = () => graph && graph.zoom(Math.max((graph.zoom() || 1) / 1.2, 0.1), { absolute: true })
const zoomToFit = () => graph && graph.zoomToFit({ padding: 10, maxScale: 1 })
const zoomReset = () => graph && graph.zoom(1)

// 格式化属性值
const formatPropertyValue = (value: any) => {
  if (value === null || value === undefined) {
    return '(空)'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

defineExpose({ loadRelation: getNeo4jData })

onMounted(() => {
  nextTick(() => {
    updateContainerHeight()
    if (parentContainerRef.value && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => updateContainerHeight())
      resizeObserver.observe(parentContainerRef.value)
    }
  })
  window.addEventListener('resize', updateContainerHeight)
  getNeo4jData()
})

onBeforeUnmount(() => {
  if (graph) {
    graph.dispose()
    graph = null
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  window.removeEventListener('resize', updateContainerHeight)
})
</script>

<template>
  <n-message-provider>
    <div
      ref="parentContainerRef"
      class="neo4j-relationship"
    >
      <svg
        style="position: fixed; top: -9999px"
        xmlns:xlink="http://www.w3.org/1999/xlink"
      >
        <defs>
          <filter
            id="filter-dropShadow-neo4j"
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

      <div class="graph-container-wrapper">
        <n-spin :show="loading">
          <div
            id="neo4j-relationship-container"
            ref="containerRef"
            class="container"
            :style="{ minHeight: `${containerHeight}px` }"
            tabindex="0"
          ></div>

          <div
            v-if="!nodeIds.length && !loading"
            class="relationship-empty"
          >
            暂无图数据库关系数据，请先保存表关系到数据库
          </div>
        </n-spin>
      </div>

      <!-- 节点信息面板 -->
      <div
        v-if="selectedNode"
        class="info-panel"
      >
        <div class="info-panel-header">
          <h3>节点信息</h3>
          <n-button
            text
            size="small"
            @click="selectedNode = null"
          >
            ✕
          </n-button>
        </div>
        <div class="node-details">
          <div class="detail-item">
            <span class="detail-label">ID:</span>
            <span class="detail-value">{{ selectedNode.id }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">名称:</span>
            <span class="detail-value">{{ selectedNode.name }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">类型:</span>
            <span class="detail-value">{{ selectedNode.category }}</span>
          </div>
          <div
            v-if="selectedNode.properties && Object.keys(selectedNode.properties).length > 0"
            class="detail-section"
          >
            <h4>属性:</h4>
            <ul class="property-list">
              <li
                v-for="(value, key) in selectedNode.properties"
                :key="key"
                class="property-item"
              >
                <span class="property-key">{{ key }}:</span>
                <span class="property-value">{{ formatPropertyValue(value) }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

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
    </div>
  </n-message-provider>
</template>

<style lang="scss" scoped>
.neo4j-relationship {
  width: 100%;
  height: 100%;
  position: relative;
  background-color: #f5f5f5; /* 参考 GraphVisualization 的背景色 */
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 15px;
}

.graph-container-wrapper {
  flex: 1;
  background: white;
  border-radius: 8px;
  padding: 15px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  min-height: 0;
  position: relative;
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
  background-color: #ffffff;

  :deep(.x6-graph),
  :deep(.x6-graph-svg) {
    width: 100%;
    height: 100%;
    transform: translateZ(0);
    will-change: transform;
  }

  :deep(.x6-node-tool) circle {
    fill: #18a0ff !important;
  }

  :deep(.x6-node) {
    cursor: move;
    filter: url("#filter-dropShadow-neo4j");
    transition: all 0.2s ease;
    
    &:hover {
      transform: scale(1.05);
    }
  }
  
  :deep(.x6-node-body) {
    transition: all 0.2s ease;
  }

  :deep(.x6-edge) {
    cursor: pointer;
    transition: opacity 0.2s ease;
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

/* 节点信息面板样式 - 参考 GraphVisualization */
.info-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 320px;
  max-height: 500px;
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  z-index: 100;
  overflow-y: auto;
}

.info-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e0e0e0;
}

.info-panel-header h3 {
  margin: 0;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.node-details {
  color: #333;
}

.detail-item {
  margin: 12px 0;
  display: flex;
  align-items: flex-start;
  line-height: 1.5;
}

.detail-label {
  font-weight: 500;
  color: #666;
  min-width: 60px;
  margin-right: 8px;
}

.detail-value {
  color: #333;
  flex: 1;
}

.detail-section {
  margin-top: 20px;
}

.detail-section h4 {
  margin: 0 0 10px 0;
  color: #555;
  font-size: 14px;
  font-weight: 600;
}

.property-list {
  margin: 0;
  padding-left: 20px;
  list-style: none;
}

.property-item {
  margin: 8px 0;
  line-height: 1.4;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}

.property-item:last-child {
  border-bottom: none;
}

.property-key {
  font-weight: 500;
  color: #666;
  margin-right: 8px;
}

.property-value {
  color: #333;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .info-panel {
    position: relative;
    top: auto;
    right: auto;
    width: 100%;
    margin-top: 15px;
  }
}
</style>

