import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/system/aimodel`

const getHeaders = () => {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

/**
 * 查询模型列表
 * @param keyword
 * @param model_type
 */
export async function fetch_model_list(keyword?: string, model_type?: number) {
  const url = new URL(`${BASE_URL}`)
  if (keyword) {
    url.searchParams.append('keyword', keyword)
  }
  if (model_type) {
    url.searchParams.append('model_type', model_type.toString())
  }
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 获取模型详情
 * @param id
 */
export async function fetch_model_detail(id: number) {
  const url = new URL(`${BASE_URL}/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 添加模型
 * @param data
 */
export async function add_model(data: any) {
  const url = new URL(`${BASE_URL}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 更新模型
 * @param data
 */
export async function update_model(data: any) {
  const url = new URL(`${BASE_URL}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'put',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 删除模型
 * @param id
 */
export async function delete_model(id: number) {
  const url = new URL(`${BASE_URL}/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'delete',
    headers: getHeaders(),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 设为默认模型
 * @param id
 */
export async function set_default_model(id: number) {
  const url = new URL(`${BASE_URL}/default/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'put',
    headers: getHeaders(),
    body: JSON.stringify({}),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 测试模型连接
 * @param data
 */
export async function check_model_status(data: any) {
  const url = new URL(`${BASE_URL}/status`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 获取基础模型列表
 * @param data
 */
export async function fetch_base_model_list(data: any) {
  const url = new URL(`${BASE_URL}/models`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req).then((res) => res.json())
}
