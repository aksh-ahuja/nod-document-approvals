import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

export function navigate(path: string) {
  window.location.hash = path
}

export function useRoute() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/')
  useEffect(() => {
    const update = () => {
      setRoute(window.location.hash.slice(1) || '/')
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return route
}

export function useApi<T>(path: string, poll = false) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(true)
  const [revision, setRevision] = useState(0)
  const loadedPath = useRef('')
  const refresh = useCallback(() => setRevision((value) => value + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    setRefreshing(true)
    if (loadedPath.current !== path) {
      setLoading(true)
      setData(null)
    }
    api<T>(path, { signal: controller.signal })
      .then((result) => {
        loadedPath.current = path
        setData(result)
        setError(null)
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setError(error)
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
          setRefreshing(false)
        }
      })
    return () => controller.abort()
  }, [path, revision])
  useEffect(() => {
    if (!poll) return
    const tick = () => {
      if (!document.hidden) refresh()
    }
    const timer = window.setInterval(tick, 20000)
    window.addEventListener('focus', tick)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', tick)
    }
  }, [poll, refresh])
  return { data, error, loading, refreshing, refresh }
}
