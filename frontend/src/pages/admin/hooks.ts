import { useCallback, useEffect, useState, type DependencyList } from 'react'
import { adminErrorMessage } from '../../services/adminApi'

/** Loads data for an admin tab and keeps the previous result on screen while it refetches. */
export function useAdminQuery<T>(fetcher: () => Promise<T>, deps: DependencyList, errorText: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetcher()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(adminErrorMessage(err, errorText))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((value) => value + 1), [])
  return { data, error, loading, reload }
}
