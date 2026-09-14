import { IconInfo } from './icons'

export default function DisclaimerBox({ children, warn = false }) {
  return (
    <div className={`disclaimer-box${warn ? ' warn' : ''}`}>
      <IconInfo size={14} style={{ marginRight: 6, verticalAlign: '-2px' }} />
      {children}
    </div>
  )
}
