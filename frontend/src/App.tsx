import { AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'
import DataSourceModal from '@/components/DataSourceModal'
import Dashboard from '@/pages/Dashboard'

export default function App() {
  const { dataSource } = useAppStore()

  return (
    <AnimatePresence mode="wait">
      {!dataSource ? (
        <DataSourceModal key="modal" />
      ) : (
        <Dashboard key="dashboard" />
      )}
    </AnimatePresence>
  )
}
