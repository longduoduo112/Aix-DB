<script lang="tsx" setup>
import { useMessage } from 'naive-ui'
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import * as GlobalAPI from '@/api'

/* ---------- 登录业务 ---------- */
const form = ref({ username: 'admin', password: '123456' })
const formRef = ref()
const message = useMessage()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

/* ---------- 酷炫科技背景 (Canvas) ---------- */
// 避免使用 const 导致可能的重新赋值误判，尽管这里不应该修改
const config = {
  particleCount: 80,
  connectionDist: 120,
  mouseDist: 180,
  color: '0, 242, 254', // RGB for Cyan #00f2fe
}

class Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number

  constructor(w: number, h: number) {
    this.x = Math.random() * w
    this.y = Math.random() * h
    this.vx = (Math.random() - 0.5) * 1
    this.vy = (Math.random() - 0.5) * 1
    this.size = Math.random() * 2 + 1
  }

  update(w: number, h: number) {
    this.x += this.vx
    this.y += this.vy

    // 边界检查 - 穿过屏幕
    if (this.x < 0) {
      this.x = w
    } else if (this.x > w) {
      this.x = 0
    }
    if (this.y < 0) {
      this.y = h
    } else if (this.y > h) {
      this.y = 0
    }
  }

  draw(ctx: CanvasRenderingContext2D) {
    ctx.beginPath()
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${config.color}, 0.6)`
    ctx.fill()
  }
}

// 使用 ref 避免闭包导致的变量引用问题
const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let particles: Particle[] = []
let animationId = 0
// 将 mouse 改为普通对象，并在使用时确保安全
const mouse = { x: -1000, y: -1000 }

const initParticles = () => {
  if (!canvasRef.value) {
    return
  }
  const { innerWidth: w, innerHeight: h } = window
  canvasRef.value.width = w
  canvasRef.value.height = h

  particles = []
  const count = w < 768 ? 40 : config.particleCount
  for (let i = 0; i < count; i++) {
    particles.push(new Particle(w, h))
  }
}

const drawLines = (p: Particle, i: number) => {
  if (!ctx) {
    return
  }
  // 粒子间连线
  for (let j = i + 1; j < particles.length; j++) {
    const p2 = particles[j]
    const dx = p.x - p2.x
    const dy = p.y - p2.y
    const dist = Math.sqrt(dx * dx + dy * dy)

    if (dist < config.connectionDist) {
      ctx.beginPath()
      // 提取变量，确保不直接在模板字符串中进行复杂计算，虽然这不应该导致 const 错误，但更安全
      const alpha = 1 - dist / config.connectionDist
      ctx.strokeStyle = `rgba(${config.color}, ${alpha})`
      ctx.lineWidth = 0.5
      ctx.moveTo(p.x, p.y)
      ctx.lineTo(p2.x, p2.y)
      ctx.stroke()
    }
  }

  // 鼠标连线
  const mdx = p.x - mouse.x
  const mdy = p.y - mouse.y
  const mDist = Math.sqrt(mdx * mdx + mdy * mdy)

  if (mDist < config.mouseDist) {
    ctx.beginPath()
    // 明确声明变量
    const alpha = (1 - mDist / config.mouseDist) * 1.5
    ctx.strokeStyle = `rgba(${config.color}, ${alpha})` // 鼠标连线更亮
    ctx.lineWidth = 1
    ctx.moveTo(p.x, p.y)
    ctx.lineTo(mouse.x, mouse.y)
    ctx.stroke()
  }
}

const animate = () => {
  if (!ctx || !canvasRef.value) {
    return
  }

  try {
    ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)

    particles.forEach((p, i) => {
      p.update(canvasRef.value!.width, canvasRef.value!.height)
      p.draw(ctx!)
      drawLines(p, i)
    })

    animationId = requestAnimationFrame(animate)
  } catch (error) {
    console.error('Animation error:', error)
    cancelAnimationFrame(animationId)
  }
}

const handleMouseMove = (e: MouseEvent) => {
  mouse.x = e.clientX
  mouse.y = e.clientY
}

const startBg = () => {
  canvasRef.value = document.getElementById('bg') as HTMLCanvasElement
  if (canvasRef.value) {
    ctx = canvasRef.value.getContext('2d')
    initParticles()
    animate()
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('resize', initParticles)
  }
}

const stopBg = () => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('resize', initParticles)
}

/* ---------- 生命周期 ---------- */
onMounted(() => {
  if (userStore.isLoggedIn) {
    router.push('/')
  } else {
    startBg()
  }
})

onUnmounted(() => {
  stopBg()
})

/* ---------- 登录操作 ---------- */
const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    message.warning('请输入用户名和密码')
    return
  }

  loading.value = true
  try {
    const res = await GlobalAPI.login(form.value.username, form.value.password)
    // Check if response is ok
    if (res && res.ok) {
      const data = await res.json()
      if (data.code === 200) {
        message.success('登录成功')
        userStore.login({ token: data.data.token })
        // Use replace to avoid history stack issues
        router.replace('/')
      } else {
        message.error(data.msg || '登录失败')
      }
    } else {
      message.error('服务器响应错误')
    }
  } catch (error) {
    message.error('网络请求异常')
    console.error(error)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <canvas id="bg"></canvas>
    <div class="login-wrapper">
      <div class="header">
        <h1 class="title">
          AIX
        </h1>
        <p class="subtitle">
          大模型数据助手
        </p>
      </div>

      <n-card
        :bordered="false"
        class="login-card"
      >
        <n-form
          ref="formRef"
          size="large"
          @submit.prevent="handleLogin"
        >
          <n-form-item
            path="username"
            :show-label="false"
          >
            <n-input
              v-model:value="form.username"
              placeholder="USERNAME"
              class="tech-input"
            >
              <template #prefix>
                <div class="i-carbon-user text-cyan-400"></div>
              </template>
            </n-input>
          </n-form-item>
          <n-form-item
            path="password"
            :show-label="false"
          >
            <n-input
              v-model:value="form.password"
              type="password"
              placeholder="PASSWORD"
              class="tech-input"
              show-password-on="click"
            >
              <template #prefix>
                <div class="i-carbon-password text-cyan-400"></div>
              </template>
            </n-input>
          </n-form-item>
          <n-form-item>
            <n-button
              type="primary"
              block
              class="tech-button"
              :loading="loading"
              @click="handleLogin"
            >
              <span class="btn-text">立即登录</span>
            </n-button>
          </n-form-item>
        </n-form>
      </n-card>

      <div class="footer-decoration">
        <div class="deco-line"></div>
        <div class="deco-text">
          SECURE CONNECTION ESTABLISHED
        </div>
        <div class="deco-line"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  background: radial-gradient(ellipse at bottom, #1b2735 0%, #090a0f 100%);
  color: #fff;
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}

#bg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
}

.login-wrapper {
  position: relative;
  z-index: 10;
  width: 420px;
  padding: 40px;
  display: flex;
  flex-direction: column;
  gap: 30px;

  /* 极简玻璃态 */

  background: rgb(16 24 39 / 40%);
  backdrop-filter: blur(12px);
  border: 1px solid rgb(0 242 254 / 10%);
  border-radius: 4px;
  box-shadow: 0 0 50px rgb(0 0 0 / 50%), inset 0 0 20px rgb(0 242 254 / 5%);
}

/* 四角装饰 */

.login-wrapper::before,
.login-wrapper::after {
  content: '';
  position: absolute;
  width: 20px;
  height: 20px;
  border: 2px solid #00f2fe;
  transition: all 0.3s;
}

.login-wrapper::before {
  top: -2px;
  left: -2px;
  border-right: none;
  border-bottom: none;
}

.login-wrapper::after {
  bottom: -2px;
  right: -2px;
  border-left: none;
  border-top: none;
}

.header {
  text-align: center;
}

.title {
  font-size: 36px;
  font-weight: 800;
  margin: 0;
  letter-spacing: 4px;
  color: #fff;
  text-shadow: 0 0 10px rgb(0 242 254 / 50%);
}

.subtitle {
  font-size: 14px;
  color: rgb(0 242 254 / 80%);
  letter-spacing: 8px;
  margin-top: 10px;
  text-transform: uppercase;
}

.login-card {
  background: transparent !important;
  border: none !important;
}

/* 输入框样式定制 */

:deep(.tech-input) {
  background-color: rgb(0 0 0 / 30%) !important;
  border: 1px solid rgb(0 242 254 / 20%) !important;
  border-radius: 2px !important;
  transition: all 0.3s ease;
}

:deep(.tech-input:hover) {
  border-color: rgb(0 242 254 / 50%) !important;
}

:deep(.tech-input.n-input--focus) {
  border-color: #00f2fe !important;
  box-shadow: 0 0 15px rgb(0 242 254 / 20%) !important;
  background-color: rgb(0 0 0 / 50%) !important;
}

:deep(.n-input__input-el) {
  color: #fff !important;
  font-family: monospace;
  letter-spacing: 1px;
}

:deep(.n-input__placeholder) {
  color: rgb(255 255 255 / 30%) !important;
  font-size: 12px;
}

/* 按钮样式 */

.tech-button {
  height: 48px;
  background: rgb(0 242 254 / 10%);
  border: 1px solid rgb(0 242 254 / 50%);
  color: #00f2fe;
  font-weight: bold;
  letter-spacing: 2px;
  border-radius: 2px;
  transition: all 0.3s;
  overflow: hidden;
  position: relative;
}

.tech-button:hover {
  background: rgb(0 242 254 / 20%);
  box-shadow: 0 0 20px rgb(0 242 254 / 40%);
  transform: translateY(-1px);
}

.tech-button:active {
  transform: translateY(1px);
}

.btn-text {
  position: relative;
  z-index: 1;
}

/* 底部装饰 */

.footer-decoration {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  margin-top: 10px;
}

.deco-line {
  height: 1px;
  flex: 1;
  background: linear-gradient(90deg, transparent, rgb(0 242 254 / 30%), transparent);
}

.deco-text {
  font-size: 10px;
  color: rgb(255 255 255 / 30%);
  letter-spacing: 1px;
}
</style>
