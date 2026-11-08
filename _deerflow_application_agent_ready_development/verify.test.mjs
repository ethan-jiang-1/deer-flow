#!/usr/bin/env node
// verify.mjs 的自测：把完整语料复制到独立临时目录，先确认有效副本通过，
// 再逐个注入违规（钉版外链违规、失效锚点、逃出语料根、缺结尾换行、SVG 缺无障碍标题），
// 断言真实入口拒绝每一种。测试不改当前语料；结束时打印并保留临时副本位置。

import { mkdtempSync, cpSync, rmSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CORPUS_ROOT, runChecks } from './verify.mjs';

const tmpBase = mkdtempSync(join(tmpdir(), 'deerflow-corpus-verify-test-'));
let failures = 0;

function makeCopy(label) {
  const dst = join(tmpBase, label);
  cpSync(CORPUS_ROOT, dst, { recursive: true });
  return dst;
}

function expectViolations(root, label, wantedRule) {
  const vs = runChecks(root);
  const hit = vs.some((v) => v.rule === wantedRule);
  if (!hit) {
    console.log(`❌ 负例未被拒绝 [${label}]：期望规则 ${wantedRule}，实际 ${vs.length} 处问题`);
    failures += 1;
  } else {
    console.log(`✅ 负例被拒绝 [${label}]（规则 ${wantedRule}）`);
  }
}

// 1. 正例：未修改的完整副本必须通过
{
  const copy = makeCopy('valid-copy');
  const vs = runChecks(copy);
  if (vs.length === 0) console.log('✅ 正例通过：未修改副本无结构问题');
  else {
    console.log(`❌ 正例失败：未修改副本有 ${vs.length} 处问题`);
    for (const v of vs) console.log(`   [${v.rule}] ${v.msg}`);
    failures += 1;
  }
}

// 2. 负例 a：非钉版外链
{
  const copy = makeCopy('bad-external');
  const readme = join(copy, 'README.md');
  writeFileSync(
    readme,
    readFileSync(readme, 'utf8') + '\n[外部链接](https://example.com/should-fail)\n',
  );
  expectViolations(copy, 'bad-external', 'pinned-external');
}

// 3. 负例 b：失效锚点
{
  const copy = makeCopy('bad-anchor');
  const index = join(copy, 'application-development-model', '00-index.md');
  writeFileSync(
    index,
    readFileSync(index, 'utf8') + '\n[坏锚点](./README.md#no-such-heading-anywhere)\n',
  );
  expectViolations(copy, 'bad-anchor', 'anchor');
}

// 4. 负例 c：相对链接逃出语料根
{
  const copy = makeCopy('escape-link');
  const index = join(copy, 'sdlc-reference', '00-index.md');
  writeFileSync(
    index,
    readFileSync(index, 'utf8') + '\n[越界链接](../../../outside-corpus.md)\n',
  );
  expectViolations(copy, 'escape-link', 'inside-corpus');
}

// 5. 负例 d：缺结尾换行
{
  const copy = makeCopy('no-newline');
  const readme = join(copy, '_coverage', 'README.md');
  const text = readFileSync(readme, 'utf8');
  writeFileSync(readme, text.endsWith('\n') ? text.slice(0, -1) : text);
  expectViolations(copy, 'no-newline', 'trailing-newline');
}

// 6. 负例 e：SVG 缺无障碍标题
{
  const copy = makeCopy('bad-svg');
  const svg = join(copy, 'application-development-model', 'figures', 'development-loop.svg');
  const text = readFileSync(svg, 'utf8').replace(/<title[\s>][\s\S]*?<\/title>/, '');
  writeFileSync(svg, text);
  expectViolations(copy, 'bad-svg', 'svg-a11y');
}

console.log('');
if (failures === 0) {
  console.log(`✅ verify 自测全部通过。临时副本保留在：${tmpBase}`);
} else {
  console.log(`❌ verify 自测有 ${failures} 个断言失败。临时副本保留在：${tmpBase}`);
  process.exit(1);
}
