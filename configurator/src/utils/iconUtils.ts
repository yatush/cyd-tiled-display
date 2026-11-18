/**
 * Convert an icon string (e.g. `\U0000e286` or legacy `"\U0000e286"`) into a
 * single displayable Unicode character for UI previews and pickers.
 */
export function iconCodeToChar(val: unknown): string {
  if (typeof val !== 'string' || !val) return '';
  let iconVal = val;
  if (iconVal.startsWith('"') && iconVal.endsWith('"') && iconVal.length >= 2) {
    iconVal = iconVal.slice(1, -1);
  }
  if (iconVal.startsWith('\\U')) {
    try {
      return String.fromCodePoint(parseInt(iconVal.substring(2), 16));
    } catch {
      return iconVal;
    }
  }
  return iconVal;
}
