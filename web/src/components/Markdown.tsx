import { lazy, Suspense, type ComponentProps } from 'react';
import PageLoading from './PageLoading';

const ReactMarkdown = lazy(() => import('react-markdown'));

export default function Markdown(props: ComponentProps<typeof ReactMarkdown>) {
  return (
    <Suspense fallback={<PageLoading />}>
      <ReactMarkdown {...props} />
    </Suspense>
  );
}
