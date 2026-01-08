import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/ds_permission`

const getHeaders = () => {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

export async function getList() {
  const url = new URL(`${BASE_URL}/list`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
  })
  return fetch(req)
}

export async function savePermissions(data: any) {
  const url = new URL(`${BASE_URL}/save`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req)
}

export async function delPermissions(id: any) {
  const url = new URL(`${BASE_URL}/delete/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
  })
  return fetch(req)
}
