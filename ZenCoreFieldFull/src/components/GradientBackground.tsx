import React from 'react';
import {Image, StyleSheet, View} from 'react-native';
import type {StyleProp, ViewStyle} from 'react-native';

/**
 * Native-module-free gradient surface for ZenCore Field.
 * Gradient PNGs are bundled assets rendered by React Native's built-in Image.
 * This avoids a Java/Kotlin ViewManager dependency in Android development builds.
 */
type Props = {
  children?: React.ReactNode;
  colors: readonly string[];
  style?: StyleProp<ViewStyle>;
  start?: {x:number;y:number};
  end?: {x:number;y:number};
  locations?: readonly number[];
  pointerEvents?: 'auto'|'none'|'box-none'|'box-only';
};

const sources = {
  hero: require('../../assets/gradients/hero.png'),
  banner: require('../../assets/gradients/banner.png'),
  metric: require('../../assets/gradients/metric.png'),
  ambient: require('../../assets/gradients/ambient.png'),
  healthGreen: require('../../assets/gradients/healthGreen.png'),
  healthBlue: require('../../assets/gradients/healthBlue.png'),
  healthAmber: require('../../assets/gradients/healthAmber.png'),
};

export default function GradientBackground({children,colors,style,pointerEvents}:Props) {
  const first=(colors[0]||'').toUpperCase();
  const key = first==='#063E78' ? 'hero'
    : first==='#07518C' ? 'banner'
    : first==='#FFFFFF' ? 'metric'
    : first==='#F3FBF7' ? 'ambient'
    : first==='#F3FFF5' ? 'healthGreen'
    : first==='#FFFDF4' ? 'healthAmber'
    : 'healthBlue';
  return (
    <View style={[style,{overflow:'hidden'}]} pointerEvents={pointerEvents}>
      <Image source={sources[key]} resizeMode="stretch" style={StyleSheet.absoluteFill} accessibilityIgnoresInvertColors />
      {children}
    </View>
  );
}
