export default function Footer() {
  return (
    <footer className="site-footer">
      <span>© {new Date().getFullYear()} SupportFlow AI</span>
      <span className="footer-separator" aria-hidden="true">•</span>
      <span>Answers grounded in your approved knowledge</span>
    </footer>
  )
}
