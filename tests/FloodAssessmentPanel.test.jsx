import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { describe, test, expect } from 'vitest'
import FloodAssessmentPanel from '../src/FloodAssessmentPanel'

describe('FloodAssessmentPanel — Phase 0 null-safety', () => {
  test('null assessment renders "not calculated", never NO', () => {
    render(<FloodAssessmentPanel assessment={null} />)
    expect(screen.getByText(/not calculated/i)).toBeInTheDocument()
    expect(screen.queryByText(/^NO$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^YES$/)).not.toBeInTheDocument()
  })

  test('insufficient_evidence status renders explicit warning, not a flag', () => {
    render(<FloodAssessmentPanel assessment={{ status: 'insufficient_evidence' }} />)
    expect(screen.getByText(/insufficient evidence/i)).toBeInTheDocument()
  })

  test('experimental status shows score and disclaimer, no binary flag', () => {
    render(<FloodAssessmentPanel assessment={{
      status: 'experimental_screening_only',
      terrain_context: {
        relative_elevation_proxy: { status: 'experimental', score: 0.4581 },
        absolute_elevation: { status: 'available', mean_m: 6.08 },
      },
    }} />)
    expect(screen.getByText(/not yet calculated/i)).toBeInTheDocument()
    expect(screen.getByText(/0.4581/)).toBeInTheDocument()
    expect(screen.getByText(/not real HAND/i)).toBeInTheDocument()
    expect(screen.queryByText(/^YES$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^NO$/)).not.toBeInTheDocument()
  })
})