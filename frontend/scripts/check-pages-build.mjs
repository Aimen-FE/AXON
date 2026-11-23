import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

export function checkPagesBuild(pagesBase) {
  let output;
  return {
    name: 'axon-check-pages-artifact',
    apply: 'build',
    configResolved(config) {
      if (config.base === pagesBase) output = resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      if (output) execFileSync(process.execPath, [
        fileURLToPath(new URL('./check-pages.mjs', import.meta.url)), output,
      ], {stdio: 'inherit'});
    },
  };
}
