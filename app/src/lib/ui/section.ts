/** Which primary tab a route belongs to. */
export function section(routeId: string | null): 'home' | 'trains' | 'settings' {
	if (!routeId || routeId === '/') return 'home';
	if (routeId.startsWith('/settings')) return 'settings';
	return 'trains';
}
