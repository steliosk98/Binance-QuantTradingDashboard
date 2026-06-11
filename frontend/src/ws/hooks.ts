import { useEffect, useRef, useState } from 'react'
import { getWsManager, type TopicHandler, type WsStatus } from './manager'

export function useTopic(topic: string | null, handler: TopicHandler): void {
  const handlerRef = useRef(handler)
  useEffect(() => {
    handlerRef.current = handler
  })
  useEffect(() => {
    if (!topic) return
    return getWsManager().subscribe(topic, (data) => handlerRef.current(data))
  }, [topic])
}

export function useWsStatus(): WsStatus {
  const [status, setStatus] = useState<WsStatus>(getWsManager().status)
  useEffect(() => getWsManager().onStatus(setStatus), [])
  return status
}
