'use client'

import { useState, useEffect } from 'react'
import { LayoutTemplate, Search, Star, TrendingUp, ChevronRight } from 'lucide-react'
import { templatesApi, datasetsApi } from '@/lib/api'

interface Template {
  id: string
  name: string
  description: string
  industry: string
  tags: string[]
  is_featured: boolean
  usage_count: number
  column_mappings: Record<string, string>
  thumbnail_url?: string
}

interface Dataset {
  id: string
  name: string
  columns_meta?: { name: string }[]
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [industries, setIndustries] = useState<string[]>([])
  const [selectedIndustry, setSelectedIndustry] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  // Use modal state
  const [useModal, setUseModal] = useState<Template | null>(null)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [selectedDataset, setSelectedDataset] = useState('')
  const [columnMappings, setColumnMappings] = useState<Record<string, string>>({})
  const [using, setUsing] = useState(false)
  const [successId, setSuccessId] = useState('')

  useEffect(() => {
    Promise.all([
      templatesApi.list(),
      templatesApi.industries(),
    ]).then(([tmplRes, indRes]) => {
      setTemplates(tmplRes?.data ?? tmplRes ?? [])
      setIndustries(indRes?.data ?? indRes ?? [])
    }).finally(() => setLoading(false))
  }, [])

  const filtered = templates.filter(t => {
    const matchInd = !selectedIndustry || t.industry === selectedIndustry
    const matchSearch = !search ||
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      (t.description ?? '').toLowerCase().includes(search.toLowerCase())
    return matchInd && matchSearch
  })

  const openUseModal = async (t: Template) => {
    setUseModal(t)
    setColumnMappings({})
    setSelectedDataset('')
    const dsRes = await datasetsApi.list()
    setDatasets(dsRes?.data ?? dsRes ?? [])
  }

  const handleUse = async () => {
    if (!useModal || !selectedDataset) return
    setUsing(true)
    try {
      const res = await templatesApi.use(useModal.id, {
        dataset_id: selectedDataset,
        column_mappings: columnMappings,
      })
      const result = res?.data ?? res
      setSuccessId(result.id)
      setUseModal(null)
    } catch (e: unknown) {
      alert((e as Error).message ?? 'Failed to create dashboard')
    } finally {
      setUsing(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
    </div>
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-indigo-100 rounded-lg">
          <LayoutTemplate className="w-6 h-6 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Template Library</h1>
          <p className="text-sm text-gray-500">Start faster with industry-proven dashboard templates</p>
        </div>
      </div>

      {successId && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg flex items-center justify-between">
          <span className="text-green-800 font-medium">Dashboard created from template!</span>
          <a href={`/dashboards`} className="text-indigo-600 text-sm font-medium hover:underline flex items-center gap-1">
            View Dashboards <ChevronRight className="w-4 h-4" />
          </a>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="Search templates…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setSelectedIndustry('')}
            className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
              !selectedIndustry
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-700 border-gray-200 hover:border-indigo-300'
            }`}
          >
            All
          </button>
          {industries.map(ind => (
            <button
              key={ind}
              onClick={() => setSelectedIndustry(ind === selectedIndustry ? '' : ind)}
              className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                selectedIndustry === ind
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-700 border-gray-200 hover:border-indigo-300'
              }`}
            >
              {ind}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="text-center text-gray-500 py-16">No templates match your filters.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map(t => (
            <div key={t.id} className="bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow">
              {/* Thumbnail */}
              <div className="h-36 bg-gradient-to-br from-indigo-50 to-violet-100 flex items-center justify-center">
                {t.thumbnail_url
                  ? <img src={t.thumbnail_url} alt={t.name} className="h-full w-full object-cover" />
                  : <LayoutTemplate className="w-14 h-14 text-indigo-300" />
                }
              </div>
              <div className="p-4">
                <div className="flex items-start justify-between mb-1">
                  <h3 className="font-semibold text-gray-900">{t.name}</h3>
                  {t.is_featured && (
                    <span className="flex items-center gap-1 px-2 py-0.5 bg-amber-50 text-amber-700 text-xs rounded-full border border-amber-200">
                      <Star className="w-3 h-3" /> Featured
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-500 mb-3 line-clamp-2">{t.description}</p>
                <div className="flex flex-wrap gap-1 mb-4">
                  {t.tags.slice(0, 4).map(tag => (
                    <span key={tag} className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">{tag}</span>
                  ))}
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1 text-xs text-gray-400">
                    <TrendingUp className="w-3.5 h-3.5" /> {t.usage_count} uses
                  </span>
                  <button
                    onClick={() => openUseModal(t)}
                    className="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"
                  >
                    Use Template
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Use Template Modal */}
      {useModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="p-6 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Use: {useModal.name}</h2>
              <p className="text-sm text-gray-500 mt-1">Select a dataset and map columns</p>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dataset</label>
                <select
                  className="w-full border border-gray-200 rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  value={selectedDataset}
                  onChange={e => setSelectedDataset(e.target.value)}
                >
                  <option value="">Select dataset…</option>
                  {datasets.map(d => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>

              {Object.keys(useModal.column_mappings).length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Column Mapping</label>
                  <div className="space-y-2">
                    {Object.entries(useModal.column_mappings).map(([placeholder, hint]) => (
                      <div key={placeholder} className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 w-24 shrink-0">{placeholder}</span>
                        <input
                          className="flex-1 border border-gray-200 rounded p-1.5 text-sm"
                          placeholder={hint}
                          value={columnMappings[placeholder] ?? ''}
                          onChange={e => setColumnMappings(prev => ({ ...prev, [placeholder]: e.target.value }))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="p-6 border-t border-gray-100 flex gap-3 justify-end">
              <button
                onClick={() => setUseModal(null)}
                className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleUse}
                disabled={!selectedDataset || using}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {using ? 'Creating…' : 'Create Dashboard'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
