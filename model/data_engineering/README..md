# Data Engineering
Creating a cleaned dataset that can be used for model training

## Idea
I looked through the OSHA incident data and identified a way to code the events that mention environmental incidents.
I am going to filter down to just these incidents and then identify the environmental factors at that location on that day.
If I can get all the environmental factors at a location on that incident day, I will have a dataset of the environmental setting in relation to incident.
I also need to randomly choose an equal number of locations which did not have incidents and record the environmental factors at those locations.
If we do this, we can have a dataset that we can train off of to create a model that can predict the environmental factors that lead to these incidents.