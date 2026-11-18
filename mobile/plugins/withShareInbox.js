const { withXcodeProject } = require('expo/config-plugins');
const { build, parse } = require('@expo/plist').default;
const { copyFileSync, readFileSync, writeFileSync } = require('node:fs');
const { join } = require('node:path');

// Let expo-sharing generate and embed the extension target, then supply the
// controller that posts to the App Group using Apple's extension lifecycle.
module.exports = function withShareInbox(config) {
  return withXcodeProject(config, current => {
    const target = join(current.modRequest.platformProjectRoot, 'expo-sharing-extension');
    copyFileSync(join(__dirname, 'ios', 'ShareIntoViewController.swift'), join(target, 'ShareIntoViewController.swift'));
    const info = join(target, 'Info.plist');
    const plist = parse(readFileSync(info, 'utf8'));
    plist.CFBundleDisplayName = 'Телеосис';
    writeFileSync(info, build(plist));
    for (const item of Object.values(current.modResults.pbxXCBuildConfigurationSection())) {
      if (item?.buildSettings?.INFOPLIST_FILE?.includes('expo-sharing-extension/Info.plist')) {
        item.buildSettings.APPLICATION_EXTENSION_API_ONLY = 'YES';
      }
    }
    return current;
  });
};
