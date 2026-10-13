// node tools/build_live2d.cjs --sdk <CubismSdkForWeb>/Framework/src [--esbuild <module-dir>]
// The Cubism SDK must be obtained under its own license. No personal paths are stored.
const path = require('path');
const fs = require('fs');
const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
const sdk = args.includes('--sdk') ? path.resolve(option('--sdk')) : process.env.CUBISM_FRAMEWORK_SRC;
if (!sdk || !fs.existsSync(path.join(sdk, 'live2dcubismframework.ts'))) {
  throw Error('Pass --sdk pointing to the Cubism Web SDK Framework/src directory');
}
const esbuild = require(args.includes('--esbuild') ? path.resolve(option('--esbuild')) : 'esbuild');
const root = path.resolve(__dirname, '..');
esbuild.buildSync({
  entryPoints: [path.join(root, 'resona_desktop_pet/live2d/web/v081/main.ts')],
  outfile: path.join(root, 'resona_desktop_pet/live2d/web/v081.js'),
  alias: {'@framework': path.resolve(sdk)},
  bundle: true, platform: 'browser', format: 'esm', target: 'es2022', legalComments: 'inline',
});
console.log('Built v081.js');
