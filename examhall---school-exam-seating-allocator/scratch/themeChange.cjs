const fs = require('fs');
const path = require('path');

const colors = {
  '#F9F8F4': '#F8FAFC',
  '#F2F1EB': '#F1F5F9',
  '#E5E1D8': '#E2E8F0',
  '#3C3D37': '#0F172A',
  '#6B705C': '#2563EB',
  '#797D62': '#3B82F6',
  '#A5A58D': '#64748B',
  '#5B604C': '#1D4ED8',
  '#8B5E3C': '#1E3A8A',
  '#CB997E': '#60A5FA',
  '#DDBEA9': '#BFDBFE',
  '#FFEBE1': '#EFF6FF',
};

function walk(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    file = path.join(dir, file);
    const stat = fs.statSync(file);
    if (stat && stat.isDirectory()) {
      results = results.concat(walk(file));
    } else {
      if (file.endsWith('.tsx') || file.endsWith('.ts') || file.endsWith('.css')) {
        results.push(file);
      }
    }
  });
  return results;
}

const files = walk('./src');
files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');
  let changed = false;
  for (const [oldC, newC] of Object.entries(colors)) {
    // Case insensitive replace for hex codes
    const regex = new RegExp(oldC, 'gi');
    if (regex.test(content)) {
      content = content.replace(regex, newC);
      changed = true;
    }
  }
  if (changed) {
    fs.writeFileSync(file, content);
    console.log(`Updated ${file}`);
  }
});
