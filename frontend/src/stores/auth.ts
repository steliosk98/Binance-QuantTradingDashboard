import { create } from 'zustand'

const STORAGE_KEY = 'cryptoquant_token'

interface AuthState {
  token: string | null
  setToken: (token: string) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token:
    typeof localStorage === 'undefined'
      ? null
      : localStorage.getItem(STORAGE_KEY),
  setToken: (token) => {
    localStorage.setItem(STORAGE_KEY, token)
    set({ token })
  },
  clear: () => {
    localStorage.removeItem(STORAGE_KEY)
    set({ token: null })
  },
}))

export function getToken(): string | null {
  return useAuthStore.getState().token
}

export function clearToken(): void {
  useAuthStore.getState().clear()
}
