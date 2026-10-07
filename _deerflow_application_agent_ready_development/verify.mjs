#!/usr/bin/env node
// _deerflow_application_agent_ready_development 结构验证器
// 规则：严格 UTF-8、单个结尾换行、无 CR、Markdown 相对链接与锚点有效、
// 目录 README 必备、外链只允许钉定 v2.1.0 的 bytedance/deer-flow 地址、
// 相对链接不得逃出语料根、SVG 结构约束。
// 只使用 Node 内置模块；按本文件位置定位语料根，不按 cwd 猜路径。

import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join, relative, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const CORPUS_ROOT = fileURLToPath(new URL('.', import.meta.url));

const PINNED_HOST = 'https://github.com/bytedance/deer-flow/';
const PINNED_TAG = 'v2.1.0';
const TAG = PINNED_TAG.replace(/\./g, '\\.');
const ALLOWED_EXTERNAL = [
  new RegExp(`^${PINNED_HOST}blob/${TAG}/.+$`),
  new RegExp(`^${PINNED_HOST}tree/${TAG}/?$`),
  new RegExp(`^${PINNED_HOST}tree/${TAG}/.+$`),
  new RegExp(`^${PINNED_HOST}releases/tag/${TAG}$`),
];

const SKIP_DIRS = new Set(['.git', 'node_modules', '.DS_Store']);

export function walkFiles(root) {
  const out = [];
  const rec = (dir) => {
    for (const name of readdirSync(dir)) {
      if (SKIP_DIRS.has(name)) continue;
      const p = join(dir, name);
      const st = statSync(p);
      if (st.isDirectory()) rec(p);
      else out.push(p);
    }
  };
  rec(root);
  return out;
}

export function mdSlug(text) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[`*]/g, '')
    .replace(/[^\p{L}\p{N}\s_-]/gu, '')
    .replace(/\s+/g, '-');
}

function extractHeadings(mdText) {
  const slugs = new Set();
  for (const line of mdText.split('\n')) {
    const m = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (m) slugs.add(mdSlug(m[2]));
  }
  return slugs;
}

function extractLinks(mdText) {
  const out = [];
  const re = /\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
  let m;
  while ((m = re.exec(mdText)) !== null) out.push({ text: m[1], target: m[2] });
  return out;
}

function decodeStrict(buf, file, violations) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buf);
  } catch {
    violations.push({ file, rule: 'strict-utf8', msg: '文件不是严格 UTF-8' });
    return null;
  }
}

export function runChecks(root = CORPUS_ROOT) {
  const violations = [];
  const files = walkFiles(root);
  const mdFiles = files.filter((f) => f.endsWith('.md'));
  const svgFiles = files.filter((f) => f.endsWith('.svg'));

  const headingsByFile = new Map();

  // 1. Markdown 编码/换行/标题
  for (const file of mdFiles) {
    const buf = readFileSync(file);
    const text = decodeStrict(buf, file, violations);
    if (text === null) continue;
    if (text.includes('\r')) {
      violations.push({ file, rule: 'no-cr', msg: '包含 CR（应为 LF 换行）' });
    }
    if (!text.endsWith('\n') || text.endsWith('\n\n')) {
      violations.push({ file, rule: 'trailing-newline', msg: '必须恰好一个结尾换行' });
    }
    headingsByFile.set(file, extractHeadings(text));
  }

  // 2. 链接与锚点
  for (const file of mdFiles) {
    const text = readFileSync(file, 'utf8');
    for (const link of extractLinks(text)) {
      const t = link.target;
      if (/^https?:\/\//.test(t)) {
        if (!ALLOWED_EXTERNAL.some((re) => re.test(t))) {
          violations.push({
            file,
            rule: 'pinned-external',
            msg: `外链未钉定 ${PINNED_HOST} 的 ${PINNED_TAG}：${t}`,
          });
        }
        continue;
      }
      if (/^mailto:/.test(t)) {
        violations.push({ file, rule: 'pinned-external', msg: `不允许 mailto 链接：${t}` });
        continue;
      }
      // 相对链接（含 #anchor）
      const hashIdx = t.indexOf('#');
      const pathPart = hashIdx === -1 ? t : t.slice(0, hashIdx);
      const anchor = hashIdx === -1 ? '' : t.slice(hashIdx + 1);
      let targetFile = file;
      if (pathPart !== '') {
        const abs = resolve(dirname(file), pathPart);
        const rel = relative(root, abs);
        if (rel.startsWith('..') || rel === '') {
          violations.push({ file, rule: 'inside-corpus', msg: `相对链接逃出语料根：${t}` });
          continue;
        }
        if (!existsSync(abs)) {
          violations.push({ file, rule: 'dead-link', msg: `相对链接目标不存在：${t}` });
          continue;
        }
        if (statSync(abs).isDirectory()) {
          if (!existsSync(join(abs, 'README.md'))) {
            violations.push({ file, rule: 'dir-readme', msg: `目录链接缺 README：${t}` });
          }
          continue;
        }
        targetFile = abs;
      }
      if (anchor !== '') {
        if (targetFile.endsWith('.md')) {
          const slugs = headingsByFile.get(targetFile);
          if (!slugs || !slugs.has(anchor)) {
            violations.push({ file, rule: 'anchor', msg: `锚点在目标中不存在：${t}` });
          }
        } else {
          violations.push({ file, rule: 'anchor', msg: `非 Markdown 目标不支持锚点：${t}` });
        }
      }
    }
  }

  // 3. 含 Markdown 的目录必须有 README
  const dirs = new Set(mdFiles.map((f) => dirname(f)));
  for (const d of dirs) {
    if (!mdFiles.some((f) => f === join(d, 'README.md'))) {
      violations.push({ file: d, rule: 'dir-readme', msg: '目录含 .md 但缺 README.md' });
    }
  }

  // 4. SVG 约束（存在才检查）
  for (const file of svgFiles) {
    const text = readFileSync(file, 'utf8');
    if (!/<svg[^>]*\swidth=/.test(text) || !/<svg[^>]*\sheight=/.test(text)) {
      violations.push({ file, rule: 'svg-size', msg: 'SVG 根元素缺固有 width/height' });
    }
    if (!/<title[ >]/.test(text)) {
      violations.push({ file, rule: 'svg-a11y', msg: 'SVG 缺 <title> 无障碍标题' });
    }
    if (!/<desc[ >]/.test(text)) {
      violations.push({ file, rule: 'svg-a11y', msg: 'SVG 缺 <desc> 说明' });
    }
  }

  return violations;
}

export function main() {
  const violations = runChecks();
  if (violations.length === 0) {
    console.log('✅ 语料结构检查全部通过');
    return 0;
  }
  for (const v of violations) {
    console.log(`❌ [${v.rule}] ${relative(process.cwd(), v.file)}: ${v.msg}`);
  }
  console.log(`共 ${violations.length} 处结构问题`);
  return 1;
}

// 直接执行时跑检查；被 import 时不跑。
if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  process.exit(main());
}
