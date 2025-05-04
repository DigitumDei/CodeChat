Param([Parameter(ValueFromRemainingArguments=$true)]$Args)
$IMAGE="codechat:test"
docker build --target test -t $IMAGE .
docker run --rm $IMAGE
