import { LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { ApiError, api, errorMessage, setSessionExpiredHandler, tokenStore } from './api/client'
import type { User } from './api/types'
import { AuthForm } from './components/AuthForm'
import { Logo } from './components/Brand'
import { Workspace } from './components/Workspace'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  // With a stored token, check it before showing anything.
  const [checking, setChecking] = useState(() => tokenStore.get() !== null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null)
      setNotice('Your session has expired. Please log in again.')
    })
    return () => setSessionExpiredHandler(null)
  }, [])

  useEffect(() => {
    if (!checking) return
    let active = true
    api
      .me()
      .then((me) => {
        if (active) setUser(me)
      })
      .catch((caught: unknown) => {
        // A 401 has already cleared the token and set the notice.
        if (active && !(caught instanceof ApiError && caught.status === 401)) {
          setNotice(errorMessage(caught))
        }
      })
      .finally(() => {
        if (active) setChecking(false)
      })
    return () => {
      active = false
    }
  }, [checking])

  function logOut() {
    tokenStore.clear()
    setUser(null)
    setNotice(null)
  }

  if (checking) {
    return (
      <div className="loading-screen">
        <Logo />
        <p className="loading-status" role="status">
          <LoaderCircle size={16} className="spin" />
          Checking your session…
        </p>
      </div>
    )
  }
  if (!user) {
    return (
      <AuthForm
        notice={notice}
        onAuthenticated={(authenticated) => {
          setNotice(null)
          setUser(authenticated)
        }}
      />
    )
  }
  // A new key per account, so nothing from a previous session is kept.
  return <Workspace key={user.id} user={user} onLogOut={logOut} />
}
