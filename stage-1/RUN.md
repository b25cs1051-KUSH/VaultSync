# Run Pocketful stage 1

```sh
docker build -t pocketful-stage-1 stage-1 && docker run --rm -e PORT=9000 -p 9000:9000 pocketful-stage-1
```
