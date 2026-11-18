Pod::Spec.new do |s|
  s.name = 'TeleiosisStorage'
  s.version = '1.0.0'
  s.summary = 'Local storage directories and share inbox for Teleiosis'
  s.description = s.summary
  s.license = { :type => 'MIT' }
  s.author = 'Teleiosis'
  s.homepage = 'https://teleiosistest.tw1.ru'
  s.source = { :git => '' }
  s.platform = :ios, '16.4'
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.source_files = '**/*.swift'
end
