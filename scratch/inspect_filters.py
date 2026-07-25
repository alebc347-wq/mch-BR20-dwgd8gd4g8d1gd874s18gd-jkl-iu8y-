import wavelink
import inspect

filters = wavelink.Filters()
print("timescale methods/attrs:")
print(dir(filters.timescale))

print("\nequalizer methods/attrs:")
print(dir(filters.equalizer))

print("\nrotation methods/attrs:")
print(dir(filters.rotation))
