import { onMounted, ref } from 'vue'
import { useI18nGlobal } from 'hooks/i18n'
import { useLoading } from 'hooks/loading'
import { api } from 'scripts/comfyAPI'

export const request = async (url: string, options?: RequestInit) => {
  return api
    .fetchApi(`/model-manager${url}`, options)
    .then(async (response: Response) => {
      // Surface HTTP error statuses (401/403/413, ...) as readable messages.
      if (!response.ok) {
        let errorMessage = `HTTP Error: ${response.status} ${response.statusText}`
        // Optimization A-7 (frontend half): a multipart upload larger than
        // ComfyUI's `client_max_size` (`--max-upload-size`, default 100 MB) is
        // rejected by the host before our route ever sees it. aiohttp answers a
        // bare 413, which used to surface as an opaque "HTTP Error: 413" -
        // translate it into the one sentence that actually helps.
        if (response.status === 413) {
          const { t } = useI18nGlobal()
          errorMessage = t('uploadTooLarge')
        }
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
    .then((resData: any) => {
      if (resData.success) {
        return resData.data
      }
      throw new Error(resData.error || 'Unknown error from server')
    })
    .catch((err: unknown) => {
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
  /** Called with the error after it has been re-thrown, for surface toasts. */
  onError?: (error: Error) => void
}

export const useRequest = <T = any>(url: string, options: RequestOptions<T> = {}) => {
  const loading = useLoading()

  const postData = options.postData ?? (data => data)
  const data = ref<T>(options.defaultValue)
  const lastParams = ref()

  const fetch = async (params: Record<string, any> = options.defaultParams ?? {}) => {
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
      .then(resData => (data.value = postData(resData)))
      .catch(err => {
        console.error(`[Request Error] ${requestUrl}:`, err)
        options.onError?.(err instanceof Error ? err : new Error(String(err)))
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
