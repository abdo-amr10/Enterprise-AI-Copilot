import { useState } from 'react'
import { IconEye, IconEyeOff } from './icons'

export default function PasswordInput({ className = '', inputClassName = '', ...inputProps }) {
  const [isVisible, setIsVisible] = useState(false)

  return (
    <div className={`password-input ${className}`.trim()}>
      <input {...inputProps} className={inputClassName} type={isVisible ? 'text' : 'password'} />
      <button
        type="button"
        className="password-visibility-toggle"
        aria-label={isVisible ? 'Hide password' : 'Show password'}
        aria-pressed={isVisible}
        onClick={() => setIsVisible((value) => !value)}
      >
        {isVisible ? <IconEyeOff aria-hidden="true" /> : <IconEye aria-hidden="true" />}
      </button>
    </div>
  )
}
