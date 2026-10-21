// ForumEditModal — edit the opening post of an existing WTRF topic (TODO-136).
// Three steps: load the live subject/BBCode body from SMF's edit form, edit,
// then review a dry-run diff from the backend before a confirmed save.

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, IconButton } from './index'
import { BASE } from '../lib/api'

type Stage = 'loading' | 'edit' | 'review' | 'saving'

interface DryRun {
  changed: string[]
  current: { subject: string; body: string }
  proposed: { subject: string; body: string }
}

const fieldStyle: React.CSSProperties = {
  padding: '8px 10px', fontSize: 'var(--lbb-fs-11-5)', fontFamily: 'var(--lbb-mono)',
  background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
  borderRadius: 6, color: 'var(--lbb-fg)', outline: 'none', lineHeight: 1.5,
}

const labelStyle: React.CSSProperties = {
  fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontWeight: 600,
}

async function postEdit(topicUrl: string, subject: string, body: string, confirm: boolean) {
  const resp = await fetch(`${BASE}/api/forum_post/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic_url: topicUrl, subject, body, confirm }),
  })
  return resp.json()
}

function DiffPane({ title, text, tone }: { title: string; text: string; tone: 'old' | 'new' }) {
  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={labelStyle}>{title}</span>
      <pre style={{
        ...fieldStyle, margin: 0, flex: 1, minHeight: 80, maxHeight: 260, overflow: 'auto',
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        borderColor: tone === 'new' ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)',
      }}>{text || '—'}</pre>
    </div>
  )
}

export function ForumEditModal({ topicUrl, onClose, onSaved }: {
  topicUrl: string
  onClose: () => void
  onSaved: (subject: string) => void
}) {
  const { t } = useTranslation()
  const [stage, setStage] = useState<Stage>('loading')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [review, setReview] = useState<DryRun | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetch(`${BASE}/api/forum_post/edit_form?topic_url=${encodeURIComponent(topicUrl)}`)
      .then(r => r.json())
      .then(d => {
        if (!live) return
        if (d.ok) { setSubject(d.subject ?? ''); setBody(d.body ?? ''); setStage('edit') }
        else setErr(d.error || t('collection.forumEdit.loadFailed'))
      })
      .catch(e => { if (live) setErr(String(e)) })
    return () => { live = false }
  }, [topicUrl, t])

  const handleReview = async () => {
    setErr(null)
    try {
      const d = await postEdit(topicUrl, subject, body, false)
      if (d.ok) { setReview(d as DryRun); setStage('review') }
      else setErr(d.error || t('collection.forumEdit.reviewFailed'))
    } catch (e) { setErr(String(e)) }
  }

  const handleConfirm = async () => {
    setErr(null); setStage('saving')
    try {
      const d = await postEdit(topicUrl, subject, body, true)
      if (d.ok && d.saved) { onSaved(d.proposed?.subject ?? subject); onClose(); return }
      setErr(d.error || t('collection.forumEdit.saveFailed'))
    } catch (e) { setErr(String(e)) }
    setStage('review')
  }

  const changed = review?.changed ?? []

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 20, width: stage === 'review' ? 860 : 640, maxWidth: '95vw',
        maxHeight: '85vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {stage === 'review' || stage === 'saving'
              ? t('collection.forumEdit.reviewTitle') : t('collection.forumEdit.modalTitle')}
          </span>
          <IconButton icon="x" size={14} title={t('common.cancel')} onClick={onClose} />
        </div>
        <div style={{
          fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)',
          marginBottom: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{topicUrl}</div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minHeight: 0, overflow: 'auto' }}>
          {stage === 'loading' && !err && (
            <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
              {t('collection.forumEdit.loading')}
            </div>
          )}

          {stage === 'edit' && (
            <>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={labelStyle}>{t('collection.forum.subject')}</span>
                <input value={subject} onChange={e => setSubject(e.target.value)} style={fieldStyle} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minHeight: 0 }}>
                <span style={labelStyle}>{t('collection.forum.body')}</span>
                <textarea
                  value={body}
                  onChange={e => setBody(e.target.value)}
                  style={{ ...fieldStyle, flex: 1, minHeight: 240, resize: 'vertical' }}
                />
              </label>
            </>
          )}

          {(stage === 'review' || stage === 'saving') && review && (
            changed.length === 0 ? (
              <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
                {t('collection.forumEdit.noChanges')}
              </div>
            ) : (
              <>
                <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-warn-fg)', background: 'var(--lbb-warn-bg)', padding: '6px 10px', borderRadius: 5 }}>
                  {t('collection.forumEdit.liveWarning')}
                </div>
                {changed.includes('subject') && (
                  <div style={{ display: 'flex', gap: 10 }}>
                    <DiffPane title={t('collection.forumEdit.currentSubject')} text={review.current.subject} tone="old" />
                    <DiffPane title={t('collection.forumEdit.newSubject')} text={review.proposed.subject} tone="new" />
                  </div>
                )}
                {changed.includes('body') && (
                  <div style={{ display: 'flex', gap: 10 }}>
                    <DiffPane title={t('collection.forumEdit.currentBody')} text={review.current.body} tone="old" />
                    <DiffPane title={t('collection.forumEdit.newBody')} text={review.proposed.body} tone="new" />
                  </div>
                )}
              </>
            )
          )}

          {err && (
            <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-err-fg)', background: 'var(--lbb-err-bg)', padding: '6px 10px', borderRadius: 5 }}>
              {err}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14, flexShrink: 0 }}>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.cancel')}</Button>
          {stage === 'edit' && (
            <Button variant="primary" size="sm" onClick={handleReview}>
              {t('collection.forumEdit.review')}
            </Button>
          )}
          {(stage === 'review' || stage === 'saving') && (
            <>
              <Button variant="ghost" size="sm" disabled={stage === 'saving'} onClick={() => setStage('edit')}>
                {t('collection.forumEdit.back')}
              </Button>
              <Button
                variant="primary" size="sm"
                disabled={stage === 'saving' || changed.length === 0}
                onClick={handleConfirm}
              >
                {stage === 'saving' ? t('collection.forumEdit.saving') : t('collection.forumEdit.confirm')}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
