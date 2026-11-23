import Ionicons from '@expo/vector-icons/Ionicons';
import { useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { colors } from '../theme';

export function MaterialThumbnail({ imageUrl, kind, size = 72 }: { imageUrl?: string | null; kind?: string; size?: number }) {
  const [failed, setFailed] = useState<string>();
  const image = imageUrl?.startsWith('https://') && failed !== imageUrl ? imageUrl : undefined;
  const placeholder = kind === 'video' ? require('../../design/icons/schematic_design_preview_video.png')
    : kind === 'article' ? require('../../design/icons/schematic_design_preview_article.png')
    : require('../../design/icons/schematic_design_preview.png');
  return <View style={[styles.frame, { width: size, height: size }]} accessible={false}>
    {image ? <Image source={{ uri: image }} onError={() => setFailed(image)} style={StyleSheet.absoluteFill} />
      : kind === 'note' || kind === 'pdf'
        ? <Ionicons name={kind === 'note' ? 'reader' : 'document-text'} color={colors.secondary} size={Math.round(size * 0.49)} />
        : <Image source={placeholder} style={{ width: size, height: size }} resizeMode="contain" />}
  </View>;
}

const styles = StyleSheet.create({
  frame: { backgroundColor: '#E9E9EB', borderRadius: 10, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});
