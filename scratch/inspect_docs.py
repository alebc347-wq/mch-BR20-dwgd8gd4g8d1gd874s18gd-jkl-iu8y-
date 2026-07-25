import wavelink
import inspect

filters = wavelink.Filters()
print("timescale.set doc:")
print(inspect.getdoc(filters.timescale.set))

print("\nequalizer.set doc:")
print(inspect.getdoc(filters.equalizer.set))

print("\nrotation.set doc:")
print(inspect.getdoc(filters.rotation.set))
