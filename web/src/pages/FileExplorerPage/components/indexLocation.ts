type IndexLocationSource = {
  page?: number | string | null;
  sheet?: string | null;
  slide?: number | string | null;
  heading?: string | null;
};

function hasValue(value: number | string | null | undefined): value is number | string {
  return value !== undefined && value !== null && value !== '';
}

export function formatIndexLocation(
  source: IndexLocationSource | null | undefined,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  if (!source) return '';
  const heading = typeof source.heading === 'string' ? source.heading.trim() : '';
  const parts: string[] = [];
  let headingUsed = false;

  if (hasValue(source.page)) {
    parts.push(t('Page {page}', { page: source.page }));
    if (heading === `第 ${source.page} 页`) headingUsed = true;
  }
  if (source.sheet) {
    parts.push(t('Sheet {name}', { name: String(source.sheet) }));
    if (heading === source.sheet) headingUsed = true;
  }
  if (hasValue(source.slide)) {
    const slidePrefix = `Slide ${source.slide}`;
    const slideLabel = t('Slide {slide}', { slide: source.slide });
    if (heading === slidePrefix) {
      parts.push(slideLabel);
      headingUsed = true;
    } else if (heading.startsWith(`${slidePrefix}:`)) {
      const title = heading.slice(slidePrefix.length + 1).trim();
      parts.push(title ? `${slideLabel}: ${title}` : slideLabel);
      headingUsed = true;
    } else {
      parts.push(slideLabel);
    }
  }
  if (heading && !headingUsed && !parts.includes(heading)) {
    parts.push(heading);
  }
  return parts.join(' · ');
}
