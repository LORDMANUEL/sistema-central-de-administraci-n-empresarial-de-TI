//go:build windows

package update

// Windows does not provide portable directory fsync semantics through os.File.Sync;
// calling Sync on a directory returns ERROR_ACCESS_DENIED on supported CI runners.
// Promotion still uses same-directory atomic renames, while staged binary contents are
// verified before activation and rollback state remains explicit.
func syncDir(string) error { return nil }
