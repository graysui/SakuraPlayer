bool isAllowedGfriendsUrl(String value) {
  if (value.contains(r'\')) return false;
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.scheme != 'https' ||
      uri.host != 'raw.githubusercontent.com' ||
      (uri.hasPort && uri.port != 443) ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment) {
    return false;
  }
  final segments = uri.pathSegments;
  const prefix = <String>['li-peifeng', 'gfriends', 'main', 'Content'];
  if (segments.length <= prefix.length) return false;
  for (var index = 0; index < prefix.length; index++) {
    if (segments[index] != prefix[index]) return false;
  }
  return !segments
      .skip(prefix.length)
      .any(
        (segment) =>
            segment.isEmpty ||
            segment == '.' ||
            segment == '..' ||
            segment.contains('/') ||
            segment.contains(r'\'),
      );
}
