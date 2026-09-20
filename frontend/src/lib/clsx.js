// Minimal clsx-alike so the UI kit has no extra runtime dependency.
export default function clsx(...args) {
  return args
    .flat(Infinity)
    .filter(Boolean)
    .join(' ')
}
