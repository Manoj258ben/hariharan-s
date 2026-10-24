// Full scan for any potential undefined variable usage in JSX pages and components
const fs = require('fs');
const path = require('path');

function getAllJSX(dir) {
  const results = [];
  const items = fs.readdirSync(dir);
  for (const item of items) {
    const full = path.join(dir, item);
    if (fs.statSync(full).isDirectory()) results.push(...getAllJSX(full));
    else if (full.endsWith('.jsx') || full.endsWith('.js')) results.push(full);
  }
  return results;
}

const files = getAllJSX('src');
const allIssues = [];

for (const file of files) {
  const content = fs.readFileSync(file, 'utf8');
  const lines = content.split('\n');
  
  // Gather declared names in this file
  const declared = new Set(['React', 'useState', 'useMemo', 'useEffect', 'useCallback', 'useRef']);
  
  // Imports
  lines.forEach(line => {
    const imp = line.match(/^import\s+(?:\{([^}]+)\}|(\w+))/);
    if (imp) {
      if (imp[1]) imp[1].split(',').forEach(n => declared.add(n.trim().split(' as ')[1]?.trim() || n.trim()));
      if (imp[2]) declared.add(imp[2]);
    }
  });
  
  // const/let/var/function declarations
  lines.forEach(line => {
    // const { a, b } = ... destructure
    const destr = line.match(/(?:const|let|var)\s+\{([^}]+)\}/g);
    if (destr) destr.forEach(d => {
      const inner = d.replace(/(?:const|let|var)\s+\{/, '').replace('}', '');
      inner.split(',').forEach(n => declared.add(n.trim().split(':')[0].trim().split(' ')[0]));
    });
    
    // const/let/var simpleVar = ...
    const simple = line.match(/(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=/g);
    if (simple) simple.forEach(d => {
      const n = d.replace(/(?:const|let|var)\s+/, '').replace(/\s*=$/, '');
      declared.add(n.trim());
    });
    
    // function foo(...) or const foo = (...) =>
    const fn = line.match(/(?:function|async function)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)/g);
    if (fn) fn.forEach(d => declared.add(d.replace(/(?:async\s+)?function\s+/, '')));
    
    // Arrow function params: (a, b) =>
    const arrowParams = line.match(/\(([^)]+)\)\s*=>/g);
    if (arrowParams) arrowParams.forEach(d => {
      const inner = d.replace(/\(/, '').replace(/\)\s*=>/, '');
      inner.split(',').forEach(n => declared.add(n.trim().replace(/=.*/, '').trim()));
    });
    
    // export const/function
    const exp = line.match(/export\s+(?:default\s+)?(?:const|function)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)/);
    if (exp) declared.add(exp[1]);
  });
  
  // Add common built-ins
  ['Math', 'Date', 'Array', 'Object', 'JSON', 'String', 'Number', 'Boolean', 'Set', 'Map',
   'console', 'window', 'document', 'localStorage', 'Promise', 'Error', 'parseInt', 'parseFloat',
   'isNaN', 'isFinite', 'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'clearTimeout',
   'setInterval', 'clearInterval', 'fetch', 'URL', 'URLSearchParams', 'FormData', 'Blob',
   'undefined', 'null', 'true', 'false', 'Infinity', 'NaN', 'Symbol', 'Proxy', 'Reflect',
   'require', 'module', 'exports', '__dirname', '__filename', 'process',
   'e', 'err', 'i', 'j', 'k', 'n', 'p', 'q', 'r', 's', 't', 'v', 'x', 'y', 'z',
   'el', 'ev', 'fn', 'cb', 'id', 'ms', 'ok', 'it'
  ].forEach(g => declared.add(g));
  
  // Now scan for .length usage on non-declared vars
  const issues = [];
  lines.forEach((line, lineIdx) => {
    // Skip comments
    if (line.trim().startsWith('//') || line.trim().startsWith('*')) return;
    
    const matches = line.matchAll(/\b([a-zA-Z_$][a-zA-Z0-9_$]*)\.(length|map|filter|forEach|reduce|find|findIndex|some|every|slice|push|pop|shift|join|includes|indexOf|sort|flat|flatMap|concat)\b/g);
    for (const m of matches) {
      const varName = m[1];
      // Skip if it looks like a prop or method chain (contains dot before it)
      const before = line.substring(0, m.index);
      if (before.endsWith('.') || before.endsWith('?.')) continue;
      
      if (!declared.has(varName)) {
        issues.push({ line: lineIdx + 1, varName, context: line.trim().substring(0, 100) });
      }
    }
  });
  
  if (issues.length > 0) {
    issues.forEach(i => allIssues.push({ file, ...i }));
  }
}

if (allIssues.length === 0) {
  console.log('No undefined variable usages found across all JSX/JS files!');
} else {
  console.log('Potential undefined variable issues (' + allIssues.length + ' found):');
  allIssues.forEach(i => {
    console.log('  [BUG] ' + i.file + ':' + i.line + ' -> "' + i.varName + '"');
    console.log('        ' + i.context);
  });
}
