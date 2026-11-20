// Exercise the filesystem APIs used by Expo/Jest after security overrides.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { test } = require('node:test');
const { Worker } = require('node:worker_threads');
const { glob, globSync, Glob } = require('glob');
const globRequire = createRequire(require.resolve('glob'));
const { minimatch } = globRequire('minimatch');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'teleiosis-toolchain-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const name of ['a.ts', '.hidden.ts', 'nested/b.md', 'excluded/c.ts', 'nested/c.txt']) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, 'synthetic fixture');
  }
  return root;
}

test('sync, promise and iterator keep source discovery and ignore semantics', async (t) => {
  const cwd = fixture(t);
  const options = { cwd, dot: true, nodir: true, ignore: ['excluded/**'] };
  const expected = ['.hidden.ts', 'a.ts', 'nested/b.md'];
  assert.deepEqual(globSync('**/*.{ts,md}', options).sort(), expected);
  assert.deepEqual((await glob('**/*.{ts,md}', options)).sort(), expected);
  const iterated = [];
  for await (const name of new Glob('**/*.{ts,md}', options)) iterated.push(name);
  assert.deepEqual(iterated.sort(), expected);
});

test('matchers preserve ordinary brace, hidden file and recursive matching', () => {
  assert.equal(minimatch('src/app/index.tsx', '**/*.{ts,tsx}'), true);
  assert.equal(minimatch('src/.hidden.ts', '**/*.ts'), false);
  assert.equal(minimatch('src/.hidden.ts', '**/*.ts', { dot: true }), true);
  assert.equal(minimatch('src/app/index.tsx', 'assets/**'), false);
});

test('the React Native Babel preset retains its legacy glob callback API', async (t) => {
  const cwd = fixture(t);
  const preset = createRequire(require.resolve('@react-native/jest-preset'));
  const babel = createRequire(preset.resolve('babel-jest'));
  const plugin = createRequire(babel.resolve('babel-plugin-istanbul'));
  const exclude = createRequire(plugin.resolve('test-exclude'));
  const legacyGlob = exclude('glob');
  const files = await new Promise((resolve, reject) => {
    legacyGlob('**/*.ts', { cwd, nodir: true, ignore: ['excluded/**'] }, (error, result) => {
      if (error) reject(error);
      else resolve(result);
    });
  });
  assert.deepEqual(files, ['a.ts']);
});

test('abort during an async walk stops scheduling directory reads', async (t) => {
  const cwd = fixture(t);
  const controller = new AbortController();
  let reads = 0;
  let atAbort;
  function abortOnce() {
    if (!controller.signal.aborted) {
      atAbort = reads;
      controller.abort();
    }
  }
  const customFs = {
    ...fs,
    readdir(file, options, callback) {
      reads++;
      const done = typeof options === 'function' ? options : callback;
      fs.readdir(file, typeof options === 'function' ? undefined : options, (error, entries) => {
        abortOnce();
        done(error, entries);
      });
    },
    promises: {
      ...fs.promises,
      async readdir(...args) {
        reads++;
        const entries = await fs.promises.readdir(...args);
        abortOnce();
        return entries;
      },
    },
  };
  await assert.rejects(glob('**/*', { cwd, fs: customFs, signal: controller.signal }), { name: 'AbortError' });
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.ok(atAbort > 0, 'the cancellation must happen inside the filesystem walk');
  assert.equal(reads, atAbort, 'cancelled traversal must not schedule more reads');
});

test('pattern amplification stays bounded in an isolated worker', { timeout: 5000 }, async () => {
  const outcome = await new Promise((resolve, reject) => {
    const worker = new Worker(`
      const { parentPort, workerData } = require('node:worker_threads');
      const { Minimatch } = require(workerData.modulePath);
      try {
        new Minimatch('**/../'.repeat(25) + '*.ts', { optimizationLevel: 2, braceExpandMax: 256 });
        parentPort.postMessage('completed');
      } catch (error) {
        if (error instanceof RangeError) parentPort.postMessage('bounded rejection');
        else throw error;
      }
    `, { eval: true, workerData: { modulePath: globRequire.resolve('minimatch') }, resourceLimits: { maxOldGenerationSizeMb: 64 } });
    const timeout = setTimeout(() => {
      void worker.terminate();
      reject(new Error('Pattern processing exceeded its resource budget'));
    }, 3000);
    worker.once('message', async (result) => {
      clearTimeout(timeout);
      await worker.terminate();
      resolve(result);
    });
    worker.once('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
  });
  assert.ok(['completed', 'bounded rejection'].includes(outcome));
});
