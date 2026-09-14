export default function Pagination({ page, pageSize, total, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(total, page * pageSize)

  return (
    <div className="pagination">
      <span>
        {total === 0 ? 'No results' : `Showing ${start}-${end} of ${total}`}
      </span>
      <div className="pagination-controls">
        <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Previous
        </button>
        <span className="muted" style={{ alignSelf: 'center' }}>
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className="btn btn-sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  )
}
