export interface Segment {
  text: string
  match: boolean
}

// The same folding the backend uses to check quotes: curly quotes, dashes and the minus sign
// become ASCII, soft hyphens disappear, whitespace runs become one space, and case is ignored.
const FOLD: Record<string, string> = {
  '‘': "'",
  '’': "'",
  '“': '"',
  '”': '"',
  '–': '-',
  '—': '-',
  '−': '-',
}
const SOFT_HYPHEN = '­'
const SPACE = /\s/

/** The folded text, and for each of its characters the index it came from in the original. */
function fold(text: string): { folded: string; origin: number[] } {
  let folded = ''
  const origin: number[] = []
  let pendingSpace = false
  for (let index = 0; index < text.length; index++) {
    const char = text[index] as string
    if (char === SOFT_HYPHEN) continue
    if (SPACE.test(char)) {
      pendingSpace = folded.length > 0
      continue
    }
    if (pendingSpace) {
      folded += ' '
      origin.push(index - 1)
      pendingSpace = false
    }
    for (const part of (FOLD[char] ?? char).toLowerCase()) {
      folded += part
      origin.push(index)
    }
  }
  return { folded, origin }
}

/** The quote without the quotation marks or final full stop a model may wrap it in. */
function foldQuote(quote: string): string {
  return fold(quote).folded.replace(/^["'.\s]+|["'.\s]+$/g, '')
}

/**
 * Splits the passage so the part matching the quote can be marked. When the quote is not found
 * word for word (after folding), the passage comes back as one unmarked segment.
 */
export function highlight(passage: string, quote: string): Segment[] {
  const needle = foldQuote(quote)
  const { folded, origin } = fold(passage)
  const at = needle ? folded.indexOf(needle) : -1
  if (at < 0) return [{ text: passage, match: false }]

  const start = origin[at] as number
  const end = (origin[at + needle.length - 1] as number) + 1
  const segments: Segment[] = [
    { text: passage.slice(0, start), match: false },
    { text: passage.slice(start, end), match: true },
    { text: passage.slice(end), match: false },
  ]
  return segments.filter((segment) => segment.text !== '')
}
