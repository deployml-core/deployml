# deployml

Welcome to deployml, a python library for deploying an end-to-end machine learning operations (MLOps) infrastructure in the cloud.

## Why was deployml created?

deployml was born out of the frustrations of teaching an MLOps course. Understanding the general concepts of MLOps is easy enough through lectures and case studies, but students wanted hands-on experience, and preferably on a truly scalable infrastructure. As I went about designing labs and homework assignments to give students what they want - the opportunity to work with ML end-to-end in the cloud - I quickly noticed a problem: many students were spending hours on just *getting things to work*. I wanted to create a tool that could facilitate the learning of the MLOps pipeline and processes, and with the help of some very dedicated graduate students, deployml is the tool we came up with. 

 The ultimate goal of deployml is to make the infrastructure part just a little bit easier so that more time can be spent on actually using the infrastructure to practice with developing, deploying, and monitoring machine learning models. 

We recognize that there is a lot that can be learned by struggling with getting infrastructure to work - but we've noticed that when students spend what precious time they have simply getting it to work, they have no fuel left to explore the different stages of the MLOps pipeline. We hope that this tool gives them that freedom, while at the same time, gives students the flexibility to practice with docker, kubernetes, terraform, and cloud computing, which are essential tools for working in MLOps. 

## Who is deployml for?

deployml was created for instructors and students of MLOps. It was not designed to be used by companies seeking a tool for MLOps infrastructure. 

## What does deployml do?

deployml will provision the infrastructure needed for a basic end-to-end MLOps pipeline in Google Cloud Platform, which includes the following components:

- experiment tracking  
- model and artifact tracking and model registration  
- feature store   
- ML pipelines (e.g. training and scoring pipelines)  
- online and offline model deployment  
- model monitoring  

What is currently not included in the pipeline is:

- anything to do with LLMs and generative AI  
- scalable model development  
- data versioning and data pipelines    

In future releases, we hope to extend deployml to AWS, and make more open source tools available for the different components.