import { describe, expect, it } from 'vitest'

import { makeAnswer } from '../test/fixtures'
import { latestPerQuestion } from './useHistory'

describe('latestPerQuestion', () => {
  it('keeps the newest answer to each question', () => {
    const newest = makeAnswer({ id: 'a3', question: 'Who approves travel?' })
    const other = makeAnswer({ id: 'a2', question: 'How early must flights be booked?' })
    const older = makeAnswer({ id: 'a1', question: '  who approves TRAVEL? ' })

    expect(latestPerQuestion([newest, other, older]).map((answer) => answer.id)).toEqual([
      'a3',
      'a2',
    ])
  })
})
