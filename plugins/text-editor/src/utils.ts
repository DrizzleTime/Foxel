/**
 * 工具函数
 */

// 语言映射
export function getMonacoLanguage(ext: string): string {
  switch (ext) {
    // Web technologies
    case 'js':
    case 'jsx':
      return 'javascript';
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'html':
    case 'htm':
      return 'html';
    case 'css':
      return 'css';
    case 'scss':
    case 'sass':
      return 'scss';
    case 'less':
      return 'less';
    case 'vue':
      return 'html';

    // Data formats
    case 'json':
      return 'json';
    case 'yaml':
    case 'yml':
      return 'yaml';
    case 'xml':
      return 'xml';
    case 'toml':
      return 'ini';
    case 'ini':
    case 'cfg':
    case 'conf':
      return 'ini';

    // Programming languages
    case 'py':
      return 'python';
    case 'java':
      return 'java';
    case 'c':
      return 'c';
    case 'cpp':
    case 'cc':
    case 'cxx':
      return 'cpp';
    case 'h':
    case 'hpp':
    case 'hxx':
      return 'cpp';
    case 'php':
      return 'php';
    case 'rb':
      return 'ruby';
    case 'go':
      return 'go';
    case 'rs':
      return 'rust';
    case 'swift':
      return 'swift';
    case 'kt':
      return 'kotlin';
    case 'scala':
      return 'scala';
    case 'cs':
      return 'csharp';
    case 'fs':
      return 'fsharp';
    case 'vb':
      return 'vb';
    case 'pl':
    case 'pm':
      return 'perl';
    case 'r':
      return 'r';
    case 'lua':
      return 'lua';
    case 'dart':
      return 'dart';

    // Database
    case 'sql':
      return 'sql';

    // Shell and scripts
    case 'sh':
    case 'bash':
    case 'zsh':
    case 'fish':
      return 'shell';
    case 'ps1':
      return 'powershell';
    case 'bat':
    case 'cmd':
      return 'bat';

    // Build and config files
    case 'dockerfile':
      return 'dockerfile';
    case 'makefile':
      return 'makefile';
    case 'gradle':
      return 'groovy';
    case 'cmake':
      return 'cmake';

    // Markdown
    case 'md':
    case 'markdown':
      return 'markdown';

    // Plain text and logs
    default:
      return 'plaintext';
  }
}

