# swamphacks-project

## Actionable Items

### Saaketh (Model/Backend)

#### Actionable Items
- Do EDA on the data
- Clean necessary data
- Create hazard model using historical data
- Create backend scaffolding (with dummy endpoints)
- Find way to store data in data warehouse or place where it can be updated via pipeline
- Start populating backend dummy endpoints with functional endpoints

#### Features to Implement
- Building out the data storage and management pipelines
- Building out the Hazard Model

### Sai (Frontend)

#### Actionable Items
- Build basic scaffolding for an IOS app using either native Swift or a chosen framework
- Test if these features are possible:
  - Sending notifications
  - Taking pictures
  - Background tasks
  - Displaying locations on map
- Make a Figma mockup of the design
- Build dummy version of app with dummy endpoints

#### Features to Implement
- Nice UI showing information in concise and intuitive manner (do research about similiar apps)
  - Must show the Hazard Index
  - Must have ability for crews to view a page that has a map and list of the most dangerous sites
  - Serve notifications in real-time if API sends out a lightning strike warning
  - Serve notifications at 6pm daily with summary
  - Have ability for crew to report hazards with picture

## Plan
Combining series of information sources into a unified database that can be used to extract real-time insights.

It will be able to:
- watch the environment around every job site to keep utility field crews safe by bringing scattered hazard data together
  - combine planet conditions like weather, extreme heat, lightning, flooding, wildfire, soil saturation, and wildlife sightings into one picture per site.
- It should warn crews as soon as risk spikes. For example:
  - Lightning: any strike within 10 miles triggers a stop-work alert with a 30-minute all-clear countdown that restarts with each new strike
  - Flooding: sites along rivers, such as the Mississippi, get a flood-risk warning after a night of heavy rain 
- Daily next-day safety briefing: Every day at 6pm it sends a next-day safety report
- Crew hazard reporting
- Supervisor PlanIt Dashboard: A map that ranks sites by risk, showing supervisors where to focus their attention and resources first
- Hazard Index (0-10): A machine learning (ML) model trained on historical weather and and environmental data that on-site workers actually face

## Targeted Tracks:

### Sperry Tech - PlanIt Control
- Info at https://docs.google.com/document/d/1lSneAISdt1fvl3DUAJB92kY8xbxe0MOy/edit

### Artificial Intelligence (Most Creative Use of AI) Brought to you by UF Data Science & Informatics
- Details:

Awarded to projects that demonstrate clear novelty and technical depth in AI/ML, with emphasis on non-trivial implementations and good coding conventions.

Requirements:

- AI/ML must be central to the project and should include but not limited to, fine-tuning, RAG pipelines, agents, custom models, evals, etc.
- A public repo must be linked on Devpost, with a README.

Note:

- We value depth over polish. A well-engineered, well-reasoned model beats a good demo. We will be reading Githubs and code
- Clean, readable, documented code counts
- Teams should be able to explain design choices and tradeoffs, not just results

Prize:

Brick (x4)