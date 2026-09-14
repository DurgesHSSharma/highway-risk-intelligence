import { Link } from 'react-router-dom'
import { EmptyState } from '../components/StateViews'

export default function NotFound() {
  return (
    <EmptyState
      title="Page not found."
      message={
        <>
          That route doesn't exist. <Link to="/">Return to the dashboard</Link>.
        </>
      }
    />
  )
}
