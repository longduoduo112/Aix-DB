<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import type { PropType } from 'vue'
import { useBusinessStore } from '@/store/business'
import type { DataTableColumns } from 'naive-ui'
import { NDataTable, NCard } from 'naive-ui'
import { Pie, Column, Line } from '@antv/g2plot'
import type { PieOptions, ColumnOptions, LineOptions, Plot } from '@antv/g2plot'

const props = defineProps({
  chartId: {
    type: String,
    required: true,
  },
  chartData: {
    type: Object as PropType<{
      template_code?: string
      columns?: string[]
      data?: any[]
    } | null>,
    default: null,
  },
})

// 自定义事件用于 子父组件传递事件信息
const emit = defineEmits(['chartRendered', 'tableRendered'])

// 全局存储
const businessStore = useBusinessStore()

// 获取数据
// 优先使用 props.chartData（历史对话数据隔离），否则使用全局 store（实时对话）
const chartData = computed(() => {
  // 优先使用 props.chartData（历史对话），否则使用全局 store（实时对话）
  if (props.chartData) {
    return props.chartData
  }
  
  const writerList = businessStore.writerList
  return writerList?.data || {}
})
const templateCode = computed(() => chartData.value?.template_code || '')
const columns = computed(() => chartData.value?.columns || [])
const data = computed(() => chartData.value?.data || [])

// 图表容器引用
const chartContainerRef = ref<HTMLElement | null>(null)
let chartInstance: Plot<any> | null = null

// 表格相关的 computed
const tableColumns = computed<DataTableColumns<any>>(() => {
  if (columns.value.length === 0 || data.value.length === 0) {
    return []
  }
  
  return columns.value.map((colName: string) => ({
    title: colName,
    key: colName,
    width: 120,
    minWidth: 80,
    maxWidth: 200,
    ellipsis: {
      tooltip: true,
    },
  }))
})

// 计算表格横向滚动宽度（根据列数和列宽动态计算）
const tableScrollX = computed(() => {
  const colCount = columns.value.length
  if (colCount === 0) {
    return undefined
  }
  // 根据列数和列宽计算，每列平均宽度约150px，确保有足够空间
  return colCount * 150
})

// 分页配置
const pagination = ref({
  page: 1,
  pageSize: 10,
  showSizePicker: true,
  pageSizes: [5, 10, 20],
  onChange: (page: number) => {
    pagination.value.page = page
  },
  onUpdatePageSize: (pageSize: number) => {
    pagination.value.pageSize = pageSize
    pagination.value.page = 1
  },
})

// 图表标题映射
const chartTitleMap: Record<string, string> = {
  temp01: '表格',
  temp02: '饼图',
  temp03: '柱状图',
  temp04: '折线图',
}

const chartTitle = computed(() => chartTitleMap[templateCode.value] || '图表')

// 现代化配色方案
const modernColorPalette = [
  '#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe',
  '#43e97b', '#fa709a', '#fee140', '#30cfd0', '#330867',
  '#a8edea', '#fed6e3', '#ffecd2', '#fcb69f', '#ff9a9e',
  '#a18cd1', '#fbc2eb', '#ffd1dc', '#ffecd2', '#d299c2'
]

// 生成渐变色配置
const getGradientColor = (color: string) => {
  return `l(0) 0:${color} 1:#ffffff`
}

// 销毁图表实例
const destroyChart = () => {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
}

// 渲染图表
const renderChart = async () => {
  if (templateCode.value === 'temp01') {
    // 表格：使用 Naive UI 的 Table（AntV 没有表格组件）
    destroyChart()
    emit('tableRendered')
    // 不清空数据，保留表格数据以便显示
    return
  }

  // 图表：使用 AntV G2Plot
  await nextTick()

  if (!chartContainerRef.value || data.value.length === 0 || columns.value.length < 2) {
    return
  }

  // 销毁旧实例
  destroyChart()

  const container = chartContainerRef.value
  const chartDataValue = data.value
  const chartColumns = columns.value

  try {
    if (templateCode.value === 'temp02') {
      // 饼图
      // 假设第一列是名称，第二列是数值
      const nameCol = chartColumns[0]
      const valueCol = chartColumns[1]
      
      const pieData = chartDataValue.map((item: any) => ({
        name: item[nameCol] || '',
        value: typeof item[valueCol] === 'number' ? item[valueCol] : Number.parseFloat(item[valueCol] || '0'),
      })).filter((item: any) => !Number.isNaN(item.value) && item.value !== 0)

      const config: PieOptions = {
        data: pieData,
        angleField: 'value',
        colorField: 'name',
        radius: 0.75,
        innerRadius: 0.5,
        color: modernColorPalette,
        statistic: {
          title: false,
          content: {
            style: {
              whiteSpace: 'pre-wrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              fontSize: 16,
              fontWeight: 500,
              color: '#333',
            },
            content: '',
          },
        },
        label: {
          type: 'inner',
          offset: '-50%',
          content: ({ percent, name }) => {
            const percentValue = (percent * 100).toFixed(1)
            return percentValue > 5 ? `${name}\n${percentValue}%` : ''
          },
          style: {
            fontSize: 13,
            fontWeight: 500,
            textAlign: 'center',
            fill: '#fff',
            textBaseline: 'middle',
            shadowBlur: 2,
            shadowColor: 'rgba(0, 0, 0, 0.3)',
          },
        },
        legend: {
          position: 'bottom',
          itemName: {
            style: {
              fill: '#333',
              fontSize: 13,
              fontWeight: 500,
            },
          },
          marker: {
            symbol: 'circle',
            style: {
              r: 6,
            },
          },
          itemSpacing: 20,
        },
        tooltip: {
          showTitle: true,
          showMarkers: false,
          formatter: (datum) => {
            return {
              name: datum.name,
              value: `${datum.value} (${((datum.percent || 0) * 100).toFixed(2)}%)`,
            }
          },
          domStyles: {
            'g2-tooltip': {
              background: 'rgba(255, 255, 255, 0.95)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              borderRadius: '8px',
              padding: '12px 16px',
              border: '1px solid rgba(102, 126, 234, 0.2)',
            },
            'g2-tooltip-title': {
              fontSize: '14px',
              fontWeight: 600,
              color: '#333',
              marginBottom: '8px',
            },
            'g2-tooltip-list-item': {
              fontSize: '13px',
              color: '#666',
            },
          },
        },
        interactions: [
          { type: 'element-active' },
          { type: 'pie-statistic-active' },
        ],
        animation: {
          appear: {
            animation: 'wave-in',
            duration: 1000,
          },
        },
      }

      chartInstance = new Pie(container, config)
      chartInstance.render()
    } else if (templateCode.value === 'temp03') {
      // 柱状图
      // 如果有3列：第一列是series（分组），第二列是x（分类），第三列是y（数值）
      // 如果有2列：第一列是x（分类），第二列是y（数值）
      const hasSeries = chartColumns.length >= 3
      const xCol = hasSeries ? chartColumns[1] : chartColumns[0]
      const yCol = hasSeries ? chartColumns[2] : chartColumns[1]
      const seriesCol = hasSeries ? chartColumns[0] : undefined
      
      const columnData = chartDataValue.map((item: any) => {
        const dataItem: any = {
          name: item[xCol] || '',
          value: typeof item[yCol] === 'number' ? item[yCol] : Number.parseFloat(item[yCol] || '0'),
        }
        if (seriesCol) {
          dataItem.series = item[seriesCol] || ''
        }
        return dataItem
      }).filter((item: any) => !Number.isNaN(item.value))

      // 计算X轴标签的最大长度和数据量，用于决定是否需要旋转
      const maxLabelLength = Math.max(...columnData.map((item: any) => String(item.name || '').length), 0)
      const dataCount = columnData.length
      // 当标签长度>8或数据量>10时，自动旋转45度
      const shouldRotate = maxLabelLength > 8 || dataCount > 10
      
      const config: ColumnOptions = {
        data: columnData,
        xField: 'name',
        yField: 'value',
        ...(hasSeries && seriesCol ? { seriesField: 'series' } : {}),
        columnWidthRatio: hasSeries ? 0.65 : 0.55,
        color: hasSeries ? modernColorPalette : (datum: any) => {
          // 单系列柱状图使用渐变色
          return 'l(270) 0:#667eea 1:#764ba2'
        },
        columnStyle: {
          radius: [8, 8, 0, 0],
        },
        label: {
          position: 'top' as const,
          offset: 8,
          style: {
            fill: '#333',
            fontSize: 12,
            fontWeight: 500,
            textBaseline: 'bottom',
          },
          formatter: (datum: any) => {
            const value = datum.value
            if (typeof value === 'number') {
              return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toFixed(0)
            }
            return value
          },
        },
        xAxis: {
          label: {
            autoRotate: shouldRotate,
            rotate: shouldRotate ? -45 : 0,
            autoHide: true,
            style: {
              fontSize: 12,
              fill: '#666',
            },
            formatter: (text: string) => {
              const maxLength = shouldRotate ? 15 : 12
              if (text && text.length > maxLength) {
                return text.slice(0, maxLength) + '...'
              }
              return text
            },
          },
          line: {
            style: {
              stroke: '#e0e0e0',
              lineWidth: 1,
            },
          },
          grid: {
            line: {
              style: {
                stroke: '#f0f0f0',
                lineWidth: 1,
                lineDash: [4, 4],
              },
            },
          },
          title: {
            text: xCol,
            style: {
              fontSize: 14,
              fill: '#333',
              fontWeight: 600,
            },
            spacing: 8,
          },
        },
        yAxis: {
          label: {
            style: {
              fontSize: 12,
              fill: '#666',
            },
            formatter: (text: string) => {
              const num = Number.parseFloat(text)
              if (num >= 1000) {
                return `${(num / 1000).toFixed(1)}k`
              }
              return text
            },
          },
          line: {
            style: {
              stroke: '#e0e0e0',
              lineWidth: 1,
            },
          },
          grid: {
            line: {
              style: {
                stroke: '#f0f0f0',
                lineWidth: 1,
                lineDash: [4, 4],
              },
            },
          },
          title: {
            text: yCol,
            style: {
              fontSize: 14,
              fill: '#333',
              fontWeight: 600,
            },
            spacing: 8,
          },
        },
        legend: hasSeries && seriesCol ? {
          position: 'bottom' as const,
          itemSpacing: 24,
          itemName: {
            style: {
              fill: '#333',
              fontSize: 13,
              fontWeight: 500,
            },
          },
          marker: {
            symbol: 'square',
            style: {
              r: 6,
            },
          },
        } : undefined,
        tooltip: {
          shared: true,
          showMarkers: false,
          domStyles: {
            'g2-tooltip': {
              background: 'rgba(255, 255, 255, 0.95)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              borderRadius: '8px',
              padding: '12px 16px',
              border: '1px solid rgba(102, 126, 234, 0.2)',
            },
            'g2-tooltip-title': {
              fontSize: '14px',
              fontWeight: 600,
              color: '#333',
              marginBottom: '8px',
            },
            'g2-tooltip-list-item': {
              fontSize: '13px',
              color: '#666',
            },
          },
        },
        interactions: [
          { type: 'element-active' },
          { type: 'element-highlight' },
        ],
        animation: {
          appear: {
            animation: 'scale-in-y',
            duration: 800,
          },
          update: {
            animation: 'scale-in-y',
            duration: 400,
          },
        },
      }

      chartInstance = new Column(container, config)
      chartInstance.render()
    } else if (templateCode.value === 'temp04') {
      // 折线图
      // 假设第一列是 x 轴，第二列是 y 轴
      const xCol = chartColumns[0]
      const yCol = chartColumns[1]
      
      // 处理数据并检测是否为日期格式
      let lineData = chartDataValue.map((item: any) => ({
        name: item[xCol] || '',
        value: typeof item[yCol] === 'number' ? item[yCol] : Number.parseFloat(item[yCol] || '0'),
        originalName: item[xCol] || '', // 保存原始值用于排序
      })).filter((item: any) => !Number.isNaN(item.value))

      // 检测第一个数据点是否为日期格式
      const isDateFormat = lineData.length > 0 && /^\d{4}-\d{2}-\d{2}/.test(lineData[0].originalName)
      
      // 如果是日期格式，按日期排序
      if (isDateFormat) {
        lineData = lineData.sort((a: any, b: any) => {
          const dateA = new Date(a.originalName).getTime()
          const dateB = new Date(b.originalName).getTime()
          return dateA - dateB
        })
      }

      // 移除临时字段
      lineData = lineData.map((item: any) => ({
        name: item.name,
        value: item.value,
      }))

      const config: LineOptions = {
        data: lineData,
        xField: 'name',
        yField: 'value',
        meta: {
          name: {
            type: 'cat', // 分类类型，但数据已排序
          },
          value: {
            type: 'linear', // y 轴为线性数值
          },
        },
        color: '#667eea',
        point: {
          size: 6,
          shape: 'circle',
          style: {
            fill: '#fff',
            stroke: '#667eea',
            lineWidth: 2,
            r: 6,
          },
        },
        lineStyle: {
          lineWidth: 3,
          stroke: '#667eea',
        },
        label: {
          position: 'top',
          offset: 10,
          style: {
            fill: '#333',
            fontSize: 12,
            fontWeight: 500,
            textBaseline: 'bottom',
          },
          formatter: (datum: any) => {
            const value = datum.value
            if (typeof value === 'number') {
              return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toFixed(0)
            }
            return value
          },
        },
        xAxis: {
          tickCount: lineData.length > 20 ? 15 : undefined, // 数据点多时限制显示的刻度数量
          label: {
            autoRotate: lineData.length > 15, // 数据点多时自动旋转
            rotate: lineData.length > 15 ? -45 : 0, // 旋转角度
            autoHide: false, // 不自动隐藏，确保标签显示
            autoEllipsis: true, // 自动省略过长文本
            style: {
              fontSize: 12,
              fill: '#666',
            },
            formatter: (text: string) => {
              if (!text) return ''
              // 如果是日期格式，尝试格式化
              if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
                // 日期格式：2024-01-05 -> 01-05
                const date = new Date(text)
                if (!isNaN(date.getTime())) {
                  const month = String(date.getMonth() + 1).padStart(2, '0')
                  const day = String(date.getDate()).padStart(2, '0')
                  return `${month}-${day}`
                }
              }
              // 如果文本过长，截断
              const maxLength = 10
              if (text.length > maxLength) {
                return text.slice(0, maxLength) + '...'
              }
              return text
            },
          },
          tickLine: {
            style: {
              stroke: '#e0e0e0',
              lineWidth: 1,
            },
          },
          line: {
            style: {
              stroke: '#e0e0e0',
              lineWidth: 1,
            },
          },
          grid: {
            line: {
              style: {
                stroke: '#f0f0f0',
                lineWidth: 1,
                lineDash: [4, 4],
              },
            },
          },
          title: {
            text: xCol,
            style: {
              fontSize: 14,
              fill: '#333',
              fontWeight: 600,
            },
            spacing: 8,
          },
        },
        yAxis: {
          label: {
            style: {
              fontSize: 12,
              fill: '#666',
            },
            formatter: (text: string) => {
              const num = Number.parseFloat(text)
              if (num >= 1000) {
                return `${(num / 1000).toFixed(1)}k`
              }
              return text
            },
          },
          line: {
            style: {
              stroke: '#e0e0e0',
              lineWidth: 1,
            },
          },
          grid: {
            line: {
              style: {
                stroke: '#f0f0f0',
                lineWidth: 1,
                lineDash: [4, 4],
              },
            },
          },
          title: {
            text: yCol,
            style: {
              fontSize: 14,
              fill: '#333',
              fontWeight: 600,
            },
            spacing: 8,
          },
        },
        smooth: true,
        tooltip: {
          showMarkers: true,
          marker: {
            symbol: 'circle',
            style: {
              r: 6,
              fill: '#667eea',
              stroke: '#fff',
              lineWidth: 2,
            },
          },
          domStyles: {
            'g2-tooltip': {
              background: 'rgba(255, 255, 255, 0.95)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              borderRadius: '8px',
              padding: '12px 16px',
              border: '1px solid rgba(102, 126, 234, 0.2)',
            },
            'g2-tooltip-title': {
              fontSize: '14px',
              fontWeight: 600,
              color: '#333',
              marginBottom: '8px',
            },
            'g2-tooltip-list-item': {
              fontSize: '13px',
              color: '#666',
            },
          },
        },
        interactions: [
          { type: 'element-active' },
        ],
        animation: {
          appear: {
            animation: 'fade-in',
            duration: 800,
          },
          update: {
            animation: 'fade-in',
            duration: 400,
          },
        },
        // 当数据点较多时，添加 x 轴滑块
        slider: lineData.length > 15 ? {
          start: 0,
          end: 1,
          height: 24,
          trendCfg: {
            areaStyle: {
              fill: 'rgba(102, 126, 234, 0.2)',
            },
            lineStyle: {
              stroke: '#667eea',
              lineWidth: 2,
            },
            point: {
              visible: false,
            },
          },
          handlerStyle: {
            fill: '#667eea',
            stroke: '#667eea',
            highLightFill: '#764ba2',
          },
          textStyle: {
            fill: '#666',
            fontSize: 12,
          },
          formatter: (text: string) => {
            // 如果是日期格式，格式化显示
            if (text && /^\d{4}-\d{2}-\d{2}/.test(text)) {
              const date = new Date(text)
              if (!isNaN(date.getTime())) {
                const month = String(date.getMonth() + 1).padStart(2, '0')
                const day = String(date.getDate()).padStart(2, '0')
                return `${month}-${day}`
              }
            }
            return text
          },
        } : undefined,
      }

      chartInstance = new Line(container, config)
      chartInstance.render()
    }

    emit('chartRendered')
    // 不清空数据，保留图表数据以便显示
  } catch (error) {
    console.error('图表渲染失败:', error)
  }
}

// 监听容器引用，当容器准备好时渲染图表
watch(
  () => chartContainerRef.value,
  (newVal) => {
    if (newVal && templateCode.value && data.value.length > 0) {
      // 使用 setTimeout 确保 DOM 完全渲染
      setTimeout(() => {
        renderChart()
      }, 0)
    }
  },
  { immediate: true },
)

// 监听数据和模板代码变化
watch(() => [templateCode.value, data.value.length], () => {
  if (chartContainerRef.value && templateCode.value && data.value.length > 0) {
    // 使用 setTimeout 确保 DOM 完全渲染
    setTimeout(() => {
      renderChart()
    }, 0)
  }
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <div class="chart-wrapper">
    <n-card
      :title="chartTitle"
      embedded
      class="modern-chart-card"
      :content-style="{
        'background': 'linear-gradient(to bottom, #fafbff 0%, #ffffff 100%)',
        'padding': '16px',
      }"
      :header-style="{
        'color': '#ffffff',
        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'padding': '18px 28px',
        'font-size': '17px',
        'font-weight': '600',
        'letter-spacing': '0.5px',
        'border-radius': '16px 16px 0 0',
        'text-align': 'left',
        'box-shadow': '0 2px 8px rgba(102, 126, 234, 0.2)',
      }"
    >
      <!-- 表格渲染 -->
      <div v-if="templateCode === 'temp01'" class="table-container">
        <n-data-table
          :columns="tableColumns"
          :data="data"
          :pagination="pagination"
          :striped="true"
          :single-line="false"
          size="small"
          :scroll-x="tableScrollX"
          :row-class-name="(row, index) => (index % 2 === 0 ? 'even-row' : 'odd-row')"
          class="modern-data-table"
        />
      </div>

      <!-- 图表容器（用于其他图表类型） -->
      <div
        v-else
        :id="chartId"
        ref="chartContainerRef"
        class="chart-container"
      />
    </n-card>
  </div>
</template>

<style scoped>
.chart-wrapper {
  background: transparent;
}

.modern-chart-card {
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(102, 126, 234, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(102, 126, 234, 0.15);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: #ffffff;
}

:deep(.modern-chart-card .n-card-header) {
  text-align: left !important;
}

:deep(.modern-chart-card .n-card-header__main) {
  text-align: left !important;
}

.modern-chart-card:hover {
  box-shadow: 0 8px 32px rgba(102, 126, 234, 0.18), 0 4px 16px rgba(0, 0, 0, 0.1);
  transform: translateY(-3px);
  border-color: rgba(102, 126, 234, 0.25);
}

.table-container {
  width: 100%;
  background: linear-gradient(135deg, #f8f9ff 0%, #ffffff 100%);
  padding: 8px;
  border-radius: 8px;
  box-shadow: inset 0 2px 8px rgba(102, 126, 234, 0.05);
}

:deep(.modern-data-table) {
  background: transparent;
  border-radius: 8px;
  overflow: hidden;
}

:deep(.n-data-table .even-row) {
  background-color: rgba(255, 255, 255, 0.9) !important;
  transition: all 0.2s ease;
}

:deep(.n-data-table .odd-row) {
  background-color: rgba(248, 250, 255, 0.9) !important;
  transition: all 0.2s ease;
}

:deep(.n-data-table .even-row:hover),
:deep(.n-data-table .odd-row:hover) {
  background: linear-gradient(90deg, rgba(102, 126, 234, 0.08) 0%, rgba(255, 255, 255, 0.9) 100%) !important;
  transform: translateX(4px);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: -2px 0 8px rgba(102, 126, 234, 0.1);
}

:deep(.n-data-table th) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
  color: #ffffff !important;
  font-weight: 600 !important;
  font-size: 13px;
  text-transform: none;
  letter-spacing: 0.3px;
  padding: 14px 16px !important;
  border: none !important;
  position: relative;
}

:deep(.n-data-table th::after) {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
}

:deep(.n-data-table td) {
  color: #2d3748 !important;
  border-bottom: 1px solid rgba(102, 126, 234, 0.08) !important;
  padding: 12px 16px !important;
  font-size: 14px;
}

:deep(.n-data-table td:first-child) {
  font-weight: 500;
  color: #1a202c;
}

:deep(.n-pagination) {
  margin-top: 24px;
  padding: 16px 0;
  border-top: 1px solid rgba(102, 126, 234, 0.1);
}

:deep(.n-pagination .n-pagination-item) {
  border-radius: 6px;
  transition: all 0.2s ease;
}

:deep(.n-pagination .n-pagination-item:not(.n-pagination-item--disabled):hover) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

:deep(.n-data-table) {
  text-align: left;
  border-radius: 8px;
}

.chart-container {
  width: 100%;
  height: 520px;
  padding: 28px;
  background: linear-gradient(to bottom, #fafbff 0%, #ffffff 100%);
  border-radius: 12px;
  position: relative;
  overflow: hidden;
  min-height: 400px;
}

.chart-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(102, 126, 234, 0.2), transparent);
}

/* 图表容器内的全局样式优化 */
:deep(.chart-container canvas) {
  border-radius: 4px;
}

/* 优化图例样式 */
:deep(.g2-legend) {
  padding: 16px 0 !important;
}

:deep(.g2-legend-list-item) {
  margin: 0 12px !important;
  padding: 4px 8px !important;
  border-radius: 4px !important;
  transition: all 0.2s ease !important;
}

:deep(.g2-legend-list-item:hover) {
  background: rgba(102, 126, 234, 0.1) !important;
}

/* 优化坐标轴样式 */
:deep(.g2-axis-line) {
  stroke: #e0e0e0 !important;
}

:deep(.g2-axis-tick-line) {
  stroke: #e0e0e0 !important;
}

/* 优化网格线样式 */
:deep(.g2-grid-line) {
  stroke: #f0f0f0 !important;
}

/* 滚动条样式优化 */
:deep(.n-data-table .n-scrollbar-rail) {
  background-color: rgba(102, 126, 234, 0.05);
}

:deep(.n-data-table .n-scrollbar-rail .n-scrollbar-rail__scrollbar) {
  background-color: rgba(102, 126, 234, 0.3);
  border-radius: 4px;
}

:deep(.n-data-table .n-scrollbar-rail .n-scrollbar-rail__scrollbar:hover) {
  background-color: rgba(102, 126, 234, 0.5);
}
</style>
