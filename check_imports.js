const fs = require('fs');
const path = require('path');

const dirs = ['src/pages', 'src/components'];
let issues = [];

dirs.forEach(dir => {
  if (!fs.existsSync(dir)) return;
  fs.readdirSync(dir).filter(f => f.endsWith('.jsx')).forEach(file => {
    const content = fs.readFileSync(path.join(dir, file), 'utf8');
    const lines = content.split('\n');
    lines.forEach((line, i) => {
      if (line.includes('import') && line.includes('from') && !line.startsWith('//')) {
        const match = line.match(/from\s+['"](.+)['"]/);
        if (match) {
          const importPath = match[1];
          if (importPath.startsWith('.')) {
            const base = path.resolve(path.join(dir, importPath));
            const exts = ['', '.js', '.jsx', '.ts', '.tsx'];
            const exists = exts.some(ext => fs.existsSync(base + ext));
            if (!exists) {
              issues.push({ file: path.join(dir, file), line: i+1, importPath });
            }
          }
        }
      }
    });
  });
});

if (issues.length === 0) {
  console.log('All relative imports OK in pages/ and components/');
} else {
  console.log('BROKEN IMPORTS FOUND:');
  issues.forEach(i => console.log('  ' + i.file + ':' + i.line + ' -> ' + i.importPath));
}
