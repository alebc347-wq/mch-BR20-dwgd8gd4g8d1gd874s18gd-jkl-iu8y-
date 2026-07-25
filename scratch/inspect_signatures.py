import wavelink
import inspect

filters = wavelink.Filters()
print("timescale.set signature:", inspect.signature(filters.timescale.set))
print("equalizer.set signature:", inspect.signature(filters.equalizer.set))
print("rotation.set signature:", inspect.signature(filters.rotation.set))
