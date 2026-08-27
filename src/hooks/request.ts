import { useLoading } from 'hooks/loading'
import { api } from 'scripts/comfyAPI'
import { onMounted, ref } from 'vue'

export const request = async (url: string, options?: RequestInit) => {
  return api
    .fetchApi(`/model-manager${url}`, options)
    .then(async (response) => {
      // 【修正】HTTPエラーステータス（401や403など）のハンドリング
      if (!response.ok) {
        let errorMessage = `HTTP Error: ${response.status} ${response.statusText}`
        try {
          const text = await response.text()
          // ComfyUI-LoginなどがHTMLを返してくる場合、JSONパースを防ぐ
          if (text.includes('<') && text.includes('>')) {
            errorMessage = `Server returned HTML (Status: ${response.status}). Please check your authentication or login status.`
          } else {
            errorMessage = text || errorMessage
          }
        } catch (e) {
          // text() の取得に失敗した場合はステータスコードのみを返す
        }
        throw new Error(errorMessage)
      }
      return response.json()
    })
    .then((resData) => {
      if (resData.success) {
        return resData.data
      }
      throw new Error(resData.error || 'Unknown error from server')
    })
    .catch((err) => {
      // JSONパースエラー（Unexpected end of JSON input など）もここでキャッチしてラップする
      if (err instanceof SyntaxError) {
        throw new Error(`Invalid JSON response from server. ${err.message}`)
      }
      throw err
    })
}

export interface RequestOptions<T> {
  method?: RequestInit['method']
  headers?: RequestInit['headers']
  defaultParams?: Record<string, any>
  defaultValue?: any
  postData?: (data: T) => T
  manual?: boolean
}

export const useRequest = <T = any>(
  url: string,
  options: RequestOptions<T> = {},
) => {
  const loading = useLoading()

  const postData = options.postData ?? ((data) => data)
  const data = ref<T>(options.defaultValue)
  const lastParams = ref()

  const fetch = async (
    params: Record<string, any> = options.defaultParams ?? {},
  ) => {
    loading.show()
    lastParams.value = params

    let requestUrl = url
    const requestOptions: RequestInit = {
      method: options.method,
      headers: options.headers,
    }

    const requestParams = { ...params }

    const templatePattern = /{(.*?)}/g
    const urlParamKeyMatches = requestUrl.matchAll(templatePattern)

    for (const urlParamKey of urlParamKeyMatches) {
      const [match, paramKey] = urlParamKey
      if (paramKey in requestParams) {
        const paramValue = requestParams[paramKey]
        delete requestParams[paramKey]
        requestUrl = requestUrl.replace(match, paramValue)
      }
    }

    if (!requestOptions.method) {
      requestOptions.method = 'GET'
    }

    if (requestOptions.method !== 'GET') {
      requestOptions.body = JSON.stringify(requestParams)
    }

    return request(requestUrl, requestOptions)
      .then((resData) => (data.value = postData(resData)))
      .catch((err) => {
        console.error(`[Request Error] ${requestUrl}:`, err)
        throw err // 呼び出し元でハンドリングできるよう再スロー
      })
      .finally(() => loading.hide())
  }

  onMounted(() => {
    if (!options.manual) {
      fetch().catch(() => {}) // 初期ロードのエラーはサイレントに処理してUIフリーズを防ぐ
    }
  })

  const refresh = async () => {
    return fetch(lastParams.value)
  }

  return { data, refresh, fetch }
}
