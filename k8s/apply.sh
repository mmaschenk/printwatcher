export NS=prusalink # Replace with your namespace

if [ "${NS}" == "" ]; then
  echo "Set the NS environment variable to your desired namespace"
  exit
fi

kubectl -n ${NS} apply -f environment.yaml
kubectl -n ${NS} apply -f deployment.yaml
