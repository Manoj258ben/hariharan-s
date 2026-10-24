const fs = require('fs');
const path = require('path');

function getFiles(dir, filter) {
  let results = [];
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat && stat.isDirectory()) {
      results = results.concat(getFiles(fullPath, filter));
    } else if (filter(fullPath)) {
      results.push(fullPath);
    }
  }
  return results;
}

const files = getFiles('src', f => f.endsWith('.jsx') || f.endsWith('.js'));
console.log(`Checking ${files.length} files...`);

const rechartsComponents = [
  'ResponsiveContainer', 'LineChart', 'Line', 'AreaChart', 'Area',
  'BarChart', 'Bar', 'PieChart', 'Pie', 'Cell', 'XAxis', 'YAxis',
  'Tooltip', 'Legend', 'CartesianGrid'
];

for (const file of files) {
  const code = fs.readFileSync(file, 'utf-8');
  for (const comp of rechartsComponents) {
    const tagRegex = new RegExp(`<${comp}[\\s/>]`);
    if (tagRegex.test(code)) {
      // check if imported or declared
      const importRegex = new RegExp(`\\b${comp}\\b`);
      const lines = code.split('\n');
      const importLines = lines.filter(l => l.includes('import ') && l.includes(comp));
      if (importLines.length === 0) {
        console.log(`[MISSING RECHARTS IMPORT] ${comp} used in ${file} but not imported!`);
      }
    }
  }
}
