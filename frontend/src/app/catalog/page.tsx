'use client'

import { useState, useEffect, useRef } from 'react'
import { BookOpen, Search, Shield, Database, Columns, TrendingUp, Tag, CheckCircle } from 'lucide-react'
import { catalogApi } from '@/lib/api'
import AppLayout from '@/components/layout/AppLayout'

interface CatalogEntry {
  id: string
  resource_type: string
  resource_id: string
  name: string
  description: string
  tags: string[]
  owner_id: string
  is_certified: boolean
  sensitivity?: string
  usage_count: number
  last_accessed?: string
  created_at?: string
}

const SENSITIVITY_COLORS: Record<string, string> = {
  public: 'bg-green-100 text-green-700',
  internal: 'bg-blue-100 text-blue-700',
  confidential: 'bg-orange-100 text-orange-700',
  restricted: 'bg-red-100 text-red-700',
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  dataset: <Database className="w-4 h-4" />,
  column: <Columns className="w-4 h-4" />,
}

export default function CatalogPage() {
  const [entries, setEntries] = useState<CatalogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [allTags, setAllTags] = useState<string[]>([])
  const [selectedTag, setSelectedTag] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<CatalogEntry | null>(null)
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = async (q = '', type = '', tag = '') => {
    setLoading(true)
    try {
      if (q) {
        const res = await catalogApi.search(q, type || undefined, tag || undefined)
        const results: CatalogEntry[] = res.data ?? res
        setEntries(results)
        setTotal(results.length)
      } else {
        const res = await catalogApi.list(type || undefined)
        const payload = res.data ?? res
        let filtered: CatalogEntry[] = payload.entries ?? payload
        if (tag) filtered = filtered.filter((e: CatalogEntry) => e.tags.includes(tag))
        setEntries(filtered)
        setTotal(payload.total ?? filtered.length)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    Promise.all([load(), catalogApi.tags()]).then(([, tagsRes]) => {
      const tags = tagsRes?.data ?? tagsRes
      setAllTags(Array.isArray(tags) ? tags : [])
    })
  }, [])

  const handleSearch = (val: string) => {
    setSearch(val)
    if (searchDebounce.current) clearTimeout(searchDebounce.current)
    searchDebounce.current = setTimeout(() => load(val, resourceType, selectedTag), 300)
  }

  const handleTypeFilter = (t: string) => {
    setResourceType(t)
    load(search, t, selectedTag)
  }

  const handleTagFilter = (tag: string) => {
    const next = tag === selectedTag ? '' : tag
    setSelectedTag(next)
    load(search, resourceType, next)
  }

  return (
    <AppLayout>
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-indigo-100 rounded-lg">
          <BookOpen className="w-6 h-6 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Data Catalog</h1>
          <p className="text-sm text-gray-500">{total} entries — discover, certify, and document your data assets</p>
        </div>
      </div>

      <div className="flex gap-6">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 space-y-6">
          {/* Type filter */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Type</p>
            {['', 'dataset', 'column'].map(t => (
              <button
                key={t || 'all'}
                onClick={() => handleTypeFilter(t)}
                className={`w-full text-left px-3 py-1.5 rounded-lg text-sm mb-1 transition-colors ${
                  resourceType === t
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                {t === '' ? 'All types' : t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          {/* Tag filter */}
          {allTags.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Tags</p>
              <div className="flex flex-wrap gap-1">
                {allTags.slice(0, 20).map(tag => (
                  <button
                    key={tag}
                    onClick={() => handleTagFilter(tag)}
                    className={`px-2 py-0.5 rounded-full text-xs transition-colors ${
                      selectedTag === tag
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-indigo-50 hover:text-indigo-700'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* Main */}
        <div className="flex-1 min-w-0">
          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="Search catalog by name or description…"
              value={search}
              onChange={e => handleSearch(e.target.value)}
            />
          </div>

          {loading ? (
            <div className="flex justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
            </div>
          ) : entries.length === 0 ? (
            <div className="text-center text-gray-500 py-16">No entries found.</div>
          ) : (
            <div className="space-y-2">
              {entries.map(entry => (
                <div
                  key={entry.id}
                  onClick={() => setSelected(selected?.id === entry.id ? null : entry)}
                  className={`bg-white border rounded-xl p-4 cursor-pointer transition-all hover:shadow-sm ${
                    selected?.id === entry.id ? 'border-indigo-400 shadow-sm' : 'border-gray-200'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className={`mt-0.5 p-1.5 rounded-lg ${entry.resource_type === 'dataset' ? 'bg-indigo-50 text-indigo-600' : 'bg-gray-100 text-gray-500'}`}>
                        {TYPE_ICONS[entry.resource_type] ?? <Database className="w-4 h-4" />}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-gray-900 truncate">{entry.name}</span>
                          {entry.is_certified && (
                            <span className="flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full shrink-0">
                              <CheckCircle className="w-3 h-3" /> Certified
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-500 truncate">{entry.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-4">
                      {entry.sensitivity && (
                        <span className={`text-xs px-2 py-0.5 rounded-full ${SENSITIVITY_COLORS[entry.sensitivity] ?? 'bg-gray-100 text-gray-600'}`}>
                          {entry.sensitivity}
                        </span>
                      )}
                      <span className="flex items-center gap-1 text-xs text-gray-400">
                        <TrendingUp className="w-3.5 h-3.5" /> {entry.usage_count}
                      </span>
                    </div>
                  </div>

                  {/* Expanded detail */}
                  {selected?.id === entry.id && (
                    <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-xs text-gray-400 mb-1">Resource ID</p>
                        <p className="font-mono text-xs text-gray-600 truncate">{entry.resource_id}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 mb-1">Type</p>
                        <p className="text-gray-700 capitalize">{entry.resource_type}</p>
                      </div>
                      {entry.tags.length > 0 && (
                        <div className="col-span-2">
                          <p className="text-xs text-gray-400 mb-1">Tags</p>
                          <div className="flex flex-wrap gap-1">
                            {entry.tags.map(tag => (
                              <span key={tag} className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full flex items-center gap-1">
                                <Tag className="w-3 h-3" /> {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {entry.last_accessed && (
                        <div>
                          <p className="text-xs text-gray-400 mb-1">Last Accessed</p>
                          <p className="text-gray-700">{new Date(entry.last_accessed).toLocaleDateString()}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
    </AppLayout>
  )
}
